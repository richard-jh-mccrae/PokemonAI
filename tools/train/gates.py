"""The two deterministic merge gates a mid-build decider swap owes (ADR-0072, #167).

#136 standing directive 6 used to grade every decider swap on a paired A/B win-rate test. Phase 1b
measured what that costs: **−1.17 pp, 95% CI [−4.59, +2.25], 0 crashes / 2400 games** — and pooled
over 4800 games, −1.06 pp, CI [−3.90, +1.78]. The run demonstrated neither a regression nor a
non-regression, and no affordable run could: clearing `CI-lo >= −1%` near a zero delta needs ~28,000
games per phase, and even then `delta >= 0` is a coin flip on a neutral swap. A mid-build swap is not
trying to raise win rate — it makes ONE axis correct in ONE currency so #165 and #145 can compose the
axes — so grading it that way measures it through the weakest consumer it will ever have.

Merit therefore lives here, in two instruments that answer **exactly** rather than statistically:

* **Decision Gate** — a Decider Lab capture diffed against a committed baseline: zero unruled
  ``REGRESSION`` frames. ADR-0069 §8's protocol, promoted from convention to a gate. It used to be
  *"the phase's ``probes/*_decider_sweep.py``"*, each comparing the agent against its own
  kill-switch OFF; ADR-0085 Amendment I replaced that once every phase's deletion pass left OFF
  scoring an empty pile (see ``decider_lab_diff``). The sweeps are diagnostics now.
* **Discrimination Gate** — a Leaf Lab capture diffed before/after: zero unruled ``OK -> MISS``
  frame flips, over all scorable frames.

Both are **per-frame, never aggregate**. Measured on 1b (`25fa8e5` vs `ac2271f`, same corrections
store, `SeededRng(0)`): the aggregate nets to −6 shared-top and −1 SOLE-top, which invites argument;
the per-frame view is **6 OK->MISS and 0 MISS->OK**, which does not — and it names the frames, so
they become rulings. The same run is why the tie metrics **report but do not gate**: avg top-tie
*fell* (3.105 -> 3.071) while six frames broke, and ties collapsed on precisely those frames
(3->1, 8->2, 9->2, 4->2, 7->1). A gate keyed on tie or distinct-value counts would have scored 1b
green.

Everything here is a pure function over plain dicts — no engine, no cgpy, no DLL, no Pilot — so the
gates are unit-testable and run in the offline cross-platform suite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: A **Lane** is the set of option shapes one Axis Claim ranks within, as
#: ``(option_type, required_select_context | None)`` members. Data, not a call-site special case:
#: the evolve lane is one plain member, while attach is ATTACH always PLUS a CARD that only counts
#: under the ATTACH_FROM context (`attach_decider_sweep.py`).
Lane = tuple

#: `cg.api`'s enums own these numbers (CLAUDE.md: engine vocabulary comes from `src/cg/api.py`), but
#: importing `cg.api` MAPS THE NATIVE LIBRARY — verified: `libcg` appears in /proc/self/maps on a bare
#: `import cg.api`. This module is the gates' pure core and must stay loadable with no DLL, the same
#: reason `planner.py` keeps its engine import lazy ("keeps the fast unit suite from ever loading the
#: native engine"). So the values are written literally and **pinned to the enums by a test**
#: (`test_lane_constants_match_the_engine_enums`), which is what makes them sourced rather than
#: remembered. Change one here and that test fails.
OPTION_TYPE_EVOLVE = 9                              # cg.api.OptionType.EVOLVE
OPTION_TYPE_ATTACH = 8                              # cg.api.OptionType.ATTACH
OPTION_TYPE_CARD = 3                                # cg.api.OptionType.CARD
SELECT_CONTEXT_ATTACH_FROM = 21                     # cg.api.SelectContext.ATTACH_FROM
SELECT_CONTEXT_SWITCH = 3                           # cg.api.SelectContext.SWITCH
SELECT_CONTEXT_TO_ACTIVE = 4                        # cg.api.SelectContext.TO_ACTIVE

EVOLVE_LANE: Lane = ((OPTION_TYPE_EVOLVE, None),)
ATTACH_LANE: Lane = ((OPTION_TYPE_ATTACH, None),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_ATTACH_FROM))
#: The promote/retreat PICK lane (ADR-0073 §12) — "promote THIS body over that one". Both the forced
#: promote and the retreat destination pose an `OptionType.CARD` option (verified against the corpus
#: and `cgpy`'s `_pose_retreat_switch`), so the lane is that type under either context.
#:
#: The whether-to-retreat frames need NO lane: `in_lane` matches type+context and cannot express a
#: tag predicate (a switch-class Item is a `_PLAY`), but Decision Claims are cross-lane by nature, so
#: the switch-Item wrinkle dissolves rather than needing a second lane.
PROMOTE_LANE: Lane = ((OPTION_TYPE_CARD, SELECT_CONTEXT_SWITCH),
                      (OPTION_TYPE_CARD, SELECT_CONTEXT_TO_ACTIVE))

OPTION_TYPE_PLAY = 7                                # cg.api.OptionType.PLAY
SELECT_CONTEXT_SETUP_BENCH = 2                      # cg.api.SelectContext.SETUP_BENCH_POKEMON
SELECT_CONTEXT_TO_BENCH = 5                         # cg.api.SelectContext.TO_BENCH
AREA_HAND = 2                                       # cg.api.AreaType.HAND

#: The DEPLOY lane (ADR-0086, Issue #197) — every way a body reaches MY Bench, which the Deploy
#: Marginal owns as one decision: a mid-game `PLAY` from hand at the main menu, the pregame
#: placement (`CARD` under SETUP_BENCH_POKEMON), and a fetch straight onto the Bench (`CARD` under
#: TO_BENCH). `PLAY` needs no context qualifier — it is only ever posed at the main menu.
DEPLOY_LANE: Lane = ((OPTION_TYPE_PLAY, None),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_SETUP_BENCH),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_TO_BENCH))

#: A held-out claim must name its owner as an issue reference — the shape CI can check offline.
#: Whether that issue is still OPEN cannot be checked here (the suite is offline, CLAUDE.md) and
#: belongs on the phase checklist.
OWNER_RE = re.compile(r"^#\d+$")

#: A held-out claim also records WHEN it was ruled, so a stale ruling is visible as an old date
#: rather than as undated prose.
RULED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hand_card_id(option: dict, frame: dict | None):
    """The id of the HAND card an option names, or None when the frame cannot resolve it.

    Fail-soft by construction — an out-of-range index, a face-down (``None``) entry or a truncated
    frame yields None rather than raising, because a probe reads whatever the corpus recorded."""
    if not frame:
        return None
    cur = frame.get("current") or {}
    players = cur.get("players") or []
    seat = option.get("playerIndex", cur.get("yourIndex", 0))     # whose zone the option indexes
    if not isinstance(seat, int) or not 0 <= seat < len(players):
        return None
    hand = (players[seat] or {}).get("hand") or []
    idx = option.get("index")
    if not isinstance(idx, int) or not 0 <= idx < len(hand):
        return None
    return (hand[idx] or {}).get("id")


def option_slot(option: dict, frame: dict | None = None) -> tuple | None:
    """The **identity** an option targets, for comparison across two deciders' picks.

    Resolution order, most specific first:

    1. a BODY in play -> ``(inPlayArea, inPlayIndex)`` — the board slot;
    2. a card in MY HAND, when ``frame`` is given -> ``("card", cardId)``;
    3. anything else naming a zone -> ``(area, index)``;
    4. otherwise None (END, YES/NO, …).

    Comparison is by slot and **never** by raw option index: two Dreepy->Drakloak evolves differ only
    in which body they evolve, and the index says nothing about which one
    (`evolve_decider_sweep.py`, ADR-0069 §8). Both decider sweeps resolved this themselves; one
    implementation here is what keeps them from drifting apart.

    **Rung 2 is ADR-0086's (Issue #197) extension, and it is why the parameter exists.** A mid-game
    bench play is `OptionType.PLAY` carrying a BARE hand index and no ``area``
    (`strategy/context.py`), so rungs 1 and 3 both miss it and the positional resolver returned None
    for exactly the options the Deploy Marginal ranks. The identity that survives a menu re-ordering
    is the CARD — "play Solrock" is one decision however the engine lists it — and the pregame Bench
    poses the same decision as `CARD` + ``area = HAND``, so both entry points must land on one
    identity or the lane compares apples to oranges.

    ``frame`` is OPTIONAL and defaults to the historical behaviour: with no frame this is
    byte-identical to the positional resolver, which is what lets the three shipped sweeps and every
    committed Axis Claim (all naming ``(4, n)`` / ``(5, n)`` board slots) keep their meaning with no
    edit. Rung 1 deliberately outranks rung 2 for the same reason — evolve, attach-from and promote
    all compare BODIES, and re-pointing them at a card id would silently re-base three sweeps."""
    if option.get("inPlayArea") is not None:
        return (option.get("inPlayArea"), option.get("inPlayIndex"))
    if frame is not None and (option.get("area") in (None, AREA_HAND)):
        cid = _hand_card_id(option, frame)
        if cid is not None:
            return ("card", cid)
    if option.get("area") is not None:
        return (option.get("area"), option.get("index"))
    return None


def in_lane(option: dict, lane: Lane, select_context=None) -> bool:
    """Is ``option`` a member of ``lane`` under ``select_context``? A member whose required context
    is None matches any context; otherwise the frame's context must equal it."""
    t = option.get("type")
    return any(t == want_type and (want_ctx is None or want_ctx == select_context)
               for want_type, want_ctx in lane)


def lane_slots(indices, options, *, lane: Lane, select_context=None, frame: dict | None = None) -> set:
    """The slots ``indices`` resolve to **within** ``lane`` (options outside the lane, and lane
    options that target no slot, contribute nothing).

    ``frame`` is forwarded to :func:`option_slot`, which is how the DEPLOY lane compares CARDS rather
    than menu positions; omitted, the resolution is the historical positional one."""
    out = set()
    for i in indices or []:
        if 0 <= i < len(options) and in_lane(options[i], lane, select_context):
            slot = option_slot(options[i], frame)
            if slot is not None:
                out.add(slot)
    return out


@dataclass(frozen=True)
class DecisionClaim:
    """*Given the whole board, the agent picks this.* The cross-lane, end-to-end assertion — the only
    thing a fixture could say before ADR-0072, and still the only thing that tests composition."""
    correct: list
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class AxisClaim:
    """*Within ONE lane, this slot outranks those.* An **ordering** claim, never a score claim: 1a
    rewrote f29 from a score claim to a decision claim because raw scores are not comparable across a
    currency re-banding. Ordering within a lane survives re-banding; cross-lane scores do not — so
    this is what stops the corpus decaying every time a currency changes.

    It deliberately cannot rescue a cross-lane defect. f32's correct answer is a retreat-to-item-lock
    wall that the evolve out-scores; an evolve-lane Axis Claim there would PASS, because the evolve
    equation does rank the right body. That frame stays a Decision-Claim failure owned by #165."""
    lane: Lane
    prefer: tuple
    over: list
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class EndorsementClaim:
    """*This slot is (or is not) taken at all.* The claim an **ordering** cannot make when a lane
    holds a single option — and single-option lanes are common.

    f35 is the case that forced it (ADR-0072 amendment A): exactly one evolve option is on the menu,
    so "prefer X over Y" is inexpressible, yet 1b's real fix there is that the premature evolve went
    **45.0 -> 0.0 with no rule firing**. This states that directly, against ``score > 0`` — the
    endorsement floor `_finish_turn_last` already gates on.

    Zero is a **structural** boundary (act / don't act), not a tuned magnitude, so this survives a
    currency re-banding exactly as ordering does. It is *not* the score claim 1a's f29 rewrite
    rejected: no magnitude is ever compared."""
    lane: Lane
    slot: tuple
    endorsed: bool
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class Claims:
    """What one corpus fixture asserts. Held-out status is **per claim, not per fixture**: f35's
    Decision Claim is owned by #165 while its Axis Claim still gates."""
    decision: DecisionClaim | None = None
    axis: list = field(default_factory=list)
    endorsement: list = field(default_factory=list)

    def all_claims(self) -> list:
        return ([self.decision] if self.decision else []) + list(self.axis) + list(self.endorsement)


def _lane_from(spec) -> Lane:
    """A fixture writes the common case as a bare ``OptionType`` int; the full member form stays
    available for a context-qualified lane like attach's."""
    if isinstance(spec, int):
        return ((spec, None),)
    return tuple((int(t), c) for t, c in spec)


def parse_claims(fixture: dict) -> Claims:
    """Read a fixture's ``claims`` block.

    **Back-compat is the reason back-fill can be incremental**: a fixture with no ``claims`` block
    yields a Decision Claim synthesised from its existing ``correct``, so all ~130 committed fixtures
    keep exactly their present meaning with no edit."""
    block = fixture.get("claims")
    if not block:
        correct = fixture.get("correct")
        return Claims(decision=DecisionClaim(correct=list(correct)) if correct else None)

    dec = None
    if block.get("decision") is not None:
        d = block["decision"]
        d = {"correct": d} if isinstance(d, list) else d
        dec = DecisionClaim(correct=list(d.get("correct") or []), owner=d.get("owner"),
                            ruled=d.get("ruled"), why=d.get("why"))
    axis = [AxisClaim(lane=_lane_from(a["lane"]),
                      prefer=tuple(a["prefer"]),
                      over=[tuple(o) for o in (a.get("over") or [])],
                      owner=a.get("owner"), ruled=a.get("ruled"), why=a.get("why"))
            for a in (block.get("axis") or [])]
    endorsement = [EndorsementClaim(lane=_lane_from(e["lane"]), slot=tuple(e["slot"]),
                                    endorsed=bool(e["endorsed"]),
                                    owner=e.get("owner"), ruled=e.get("ruled"),
                                    why=e.get("why"))
                   for e in (block.get("endorsement") or [])]
    return Claims(decision=dec, axis=axis, endorsement=endorsement)


def held_out_owner(claim) -> str | None:
    """The issue a claim has been ruled onto, or None when the claim GATES. Deleting ``owner`` is
    what returns a frame to gating — no other ceremony (ADR-0072 decision 4)."""
    return getattr(claim, "owner", None) or None


def evaluate_decision_claim(claim: DecisionClaim, *, chosen) -> bool:
    """Did the agent pick exactly what the fixture says it should?"""
    return sorted(claim.correct) == sorted(chosen or [])


def evaluate_axis_claim(claim: AxisClaim, *, options, scores, select_context=None) -> bool:
    """Does ``prefer`` **strictly** outrank every slot in ``over``, within the claim's lane?

    Strictly: a tie is not an ordering — the argmax breaks ties by option order, not by the claim, so
    a shared top would let the wrong body be picked while the claim read green. Options outside the
    lane are ignored entirely, which is the whole point: on f35 an ABILITY out-scoring the evolve
    says nothing about whether the evolve axis is right."""
    best = _lane_best(claim, options, scores, select_context)
    if claim.prefer not in best:
        return False
    return all(best[claim.prefer] > best[rival] for rival in claim.over if rival in best)


def _lane_best(claim, options, scores, select_context):
    """``{slot: best score}`` within a claim's lane — the shared basis both lane claims read."""
    best: dict = {}
    for i, opt in enumerate(options or []):
        if not in_lane(opt, claim.lane, select_context):
            continue
        slot = option_slot(opt)
        if slot is None or i >= len(scores) or scores[i] is None:
            continue
        if slot not in best or scores[i] > best[slot]:
            best[slot] = scores[i]
    return best


def evaluate_endorsement_claim(claim: EndorsementClaim, *, options, scores,
                               select_context=None) -> bool | None:
    """Does ``slot`` clear the endorsement floor (``score > 0``), and does that match the claim?

    Returns **None** when the slot is not on the menu at all — unprovable, never vacuously true. A
    claim that silently passes once its board changes underneath it is how a stale assertion outlives
    the thing it was asserting."""
    best = _lane_best(claim, options, scores, select_context)
    if claim.slot not in best:
        return None
    return (best[claim.slot] > 0) is claim.endorsed


def leaf_lab_diff(before: dict, after: dict, *, voided=()) -> dict:
    """Per-frame verdict movement between two Leaf Lab captures.

    Rows are matched on their stable ``key`` (the Correction's ``identity_key``). Keying on
    ``episode_id`` alone silently merged frames from one episode — it collapsed a real 276-row diff
    to 221 — and an under-reporting gate is the precise failure mode this exists to prevent. Frames
    present on only one side are surfaced (``added``/``removed``) rather than quietly skipped, so a
    capture taken against a different corpus shape is visible — and a frame whose *ruling* moved is
    surfaced as a **Ruling Move** (`ruling_moves`), which neither of those pairs can see because the
    frame exists on both sides. This diff compares ``correct_is_top``, computed FROM ``correct``, so
    a re-ruling silently changes its verdict exactly as it does the Decision Gate's.

    ``voided`` frames are still compared and still reported — only the gate verdict and the
    **Agree Delta** exclude them. A voided frame silently vanishing from the diff would be the
    shrinking-gated-set failure ``added``/``removed`` exist to prevent."""
    b = rows_by_key(before, keep=_scorable)
    a = rows_by_key(after, keep=_scorable)
    shared = b.keys() & a.keys()
    ok_to_miss, miss_to_ok = [], []
    for k in sorted(shared):
        was, now = bool(b[k].get("correct_is_top")), bool(a[k].get("correct_is_top"))
        if was and not now:
            ok_to_miss.append({"key": k, "before": b[k], "after": a[k]})
        elif now and not was:
            miss_to_ok.append({"key": k, "before": b[k], "after": a[k]})
    return {"ok_to_miss": ok_to_miss, "miss_to_ok": miss_to_ok,
            "added": sorted(a.keys() - b.keys()), "removed": sorted(b.keys() - a.keys()),
            "compared": len(shared),
            # SAME row filter as `compared` above, so the two numbers in one report describe one
            # population — a ruling_moves drawn from all rows would name frames `compared` excludes.
            "ruling_moves": ruling_moves(before, after, keep=_scorable),
            "agree_delta": agree_delta(
                before, after, keep=_scorable, voided=voided,
                # The Leaf Lab's ruling is `correct_is_top`; an unscorable row is already filtered out
                # by `keep`, so every surviving row is gradeable.
                agrees=lambda r: bool(r.get("correct_is_top")),
                moved=lambda x, y: bool(x.get("correct_is_top")) != bool(y.get("correct_is_top")))}


def discrimination_gate_verdict(diff: dict, *, held_out: dict, voided=()) -> bool:
    """PASS iff no frame degraded ``OK -> MISS`` without a ruling.

    Improvements never block, and the aggregate metrics (SOLE-top / shared-top / avg top-tie) are not
    consulted at all — on 1b they moved the *good* way while six frames broke.

    ``voided`` frames do not block either (ADR-TEMP-239 decision 4): their ruling can no longer say
    the agent is wrong. Passed alongside ``held_out`` rather than folded into it because the two are
    different acts — one holds a STANDING ruling out of this gate's scope, the other says the ruling
    itself cannot grade — and the readout names them separately."""
    excused = set(held_out) | set(voided or ())
    return all(f["key"] in excused for f in diff.get("ok_to_miss") or [])


def decision_gate_verdict(rows, *, held_out: dict, voided=()) -> bool:
    """PASS iff no frame carries an unruled ``REGRESSION``. ``FIX`` and ``DIVERGENT`` never block —
    the sweep puts every flip in front of the human, and only a regression they have not ruled is a
    blocker.

    A ``REGRESSION`` on a **voided** frame is reported and never blocks (ADR-TEMP-239 decision 4).
    That is the live hazard this closes: 18 of 101 recorded disagreements carried a refuted label, so
    a build that corrected one of them failed `main` for moving away from a ruling the human had
    already disowned."""
    excused = set(held_out) | set(voided or ())
    return all(r["key"] in excused
               for r in rows or [] if r.get("verdict") == "REGRESSION")


def frame_key_of(episode_id, seat, scope, subject) -> str:
    """The flat string form of a Correction's ``identity_key`` — ``episode|seat|scope|subject``.

    THE one place that shape is built. Both gates key on it and one ruling must hold a frame out of
    either, so a second implementation that drifted by a field would silently stop matching. The
    Leaf Lab passes the values straight off a Correction; the sweeps read them off the raw record."""
    return "|".join("" if p is None else str(p) for p in (episode_id, seat, scope, subject))


def print_gate_report(title, *, gating, ruled, held_out, total, rule, line,
                      voided=(), voided_by=None) -> bool:
    """Print one gate's verdict block and return whether it PASSED — shared by both gates so their
    reports cannot drift in shape or in what they claim.

    ``ruled`` frames are printed in an always-visible ``HELD OUT`` section and excluded from the
    verdict (ADR-0072 decision 4): a re-ruling is a state the gate reads, and a frame broken for
    three phases must not become scenery. ``line(item)`` renders one row.

    ``voided`` frames get their own always-visible section for the same reason and a different cause
    (ADR-TEMP-239 decision 4) — a HELD-OUT ruling STANDS and is merely out of this gate's scope,
    while a voided one cannot grade at all. Collapsing them into one section would print
    ``owner=None`` against a frame nobody held out and lose which of the two acts excused it."""
    print(f"\n=== {title} ===")
    for item in gating:
        print(f"  {line(item)}")
    if ruled:
        print(f"\n  HELD OUT ({len(ruled)}) — reported, not gated:")
        for item in ruled:
            print(f"    {line(item)}  owner={held_out.get(_key_of(item))}")
    if voided:
        print(f"\n  VOIDED ({len(voided)}) — the ruling cannot grade these; reported, not gated:")
        for item in voided:
            r = (voided_by or {}).get(_key_of(item))
            print(f"    {line(item)}  voided={getattr(r, 'disposition', '?')}")
    excused = len(ruled) + len(voided)
    print(f"\n  gated on {total - excused} frame(s), held out {len(ruled)}, voided {len(voided)}")
    passed = not gating
    print(f"GATE: {'PASS' if passed else 'FAIL'}  (rule: {rule}; {len(gating)} unruled, "
          f"{len(ruled)} ruled, {len(voided)} voided)")
    return passed


def _key_of(item) -> str:
    return item["key"] if isinstance(item, dict) else str(item)


def held_out_map(claims_by_key: dict) -> dict:
    """``{frame key: owner}`` for every claim that has been ruled onto an owner — the Held-out
    Ledger both gates consult."""
    return {k: held_out_owner(c) for k, c in claims_by_key.items() if held_out_owner(c)}


#: A **Ruling** the human recorded about a frame, wherever it was recorded. `source` names the store
#: it came from, so the **Ruling Index** doubles as the *"where is this ruled?"* register rather than
#: a bare skip-list. `owner`/`ruled` are populated only by the **Held-out Ledger**, which is the one
#: store that carries them.
@dataclass(frozen=True)
class Ruling:
    disposition: str
    source: str                       # "reviewed" | "held_out"
    reason: str = ""
    owner: str | None = None          # the Held-out Ledger's field; `reviewed.json` carries none


#: The dispositions that VOID a label — the ruling can no longer grade the agent, for two different
#: reasons. Both leave the agree-rate denominator and both stop gating (ADR-TEMP-239 decision 4).
#:
#: * ``refuted``       — the ruling is DISOWNED. It said the wrong thing.
#: * ``transposition`` — the ruling STANDS, but its ``correct`` names one of an *indistinguishable*
#:   set of options, so no agent can be scored on picking "the right one" (ADR-TEMP-239 decision 6).
#:   Kept distinct from ``refuted`` because ADR-0085 decision 4 cites `81905522-75`'s pick to justify
#:   leg-scoped rather than whole-target guards — filing it as a refutation would write into the
#:   ledger an assertion a shipped ADR contradicts. Only the instance is handled here; teaching
#:   `satisfies_human` an equivalence class over options is Issue #247.
VOIDING_DISPOSITIONS = frozenset({"refuted", "transposition"})

#: Every disposition the index UNDERSTANDS. Anything outside this is non-voiding and reported loudly
#: (`unrecognised_rulings`) rather than swallowed — the failure this guards is measured, not
#: hypothetical: `reviewed.json` carried ``fixed`` and ``deferred-multi-turn`` for weeks while
#: `blunder.reviewed.DISPOSITIONS` listed neither, so the writer's validator would have rejected
#: rows the loader accepted in silence. Both are adopted here (they are plainly rulings that STAND),
#: which is what keeps the loud path quiet today and available for the next unknown word.
RECOGNISED_DISPOSITIONS = VOIDING_DISPOSITIONS | frozenset({
    "covered", "deferred", "deferred-multi-turn", "fixed", "held_out"})


def voids_the_label(ruling) -> bool:
    """Does this **Ruling** void the human's label — the ONE predicate every grader keys on.

    Never branch on ``ruling.disposition`` at a call site. The vocabulary grows (it grew twice before
    anyone noticed), and a consumer that hardcodes *which words void* is the "each consumer needs its
    own copy" shape ADR-0087 exists to remove. Ask this instead.

    A voided frame is neither agreement nor disagreement: a ruling the human took back cannot say the
    agent was right and cannot say it was wrong. So it leaves the agree-rate DENOMINATOR and stops
    gating — the same treatment ADR-0072 decision 4 gives a **Held-out Frame**, arrived at for a
    different reason. Measured on `data/decider_lab/baseline.json` @ `e50735a`: **18 of 101 recorded
    disagreements were refuted labels**, so a build that corrected one of them failed `main` as a
    ``REGRESSION`` — a fix wearing a regression's label."""
    return getattr(ruling, "disposition", None) in VOIDING_DISPOSITIONS


def voiding_ruling(rulings):
    """The **Ruling** that voids a frame, or None — the precedence rule, in one place.

    **Any voiding source wins.** A refutation is a strictly later, stronger act than a ``covered``, so
    a merge that let a weaker disposition mask it would re-open exactly the hole this closes. Every
    ruling is retained by `ruling_index` regardless, so a readout can still name every store that
    ruled the frame."""
    for r in rulings or ():
        if voids_the_label(r):
            return r
    return None


def voided_frames(index: dict) -> dict:
    """``{frame key: the voiding Ruling}`` over a **Ruling Index** — what the gates actually consume."""
    out = {}
    for key, rulings in (index or {}).items():
        hit = voiding_ruling(rulings)
        if hit is not None:
            out[key] = hit
    return out


def unrecognised_rulings(index: dict) -> list:
    """``[(frame key, Ruling), ...]`` for every ruling whose disposition is outside
    `RECOGNISED_DISPOSITIONS` — surfaced LOUDLY, never dropped.

    An unknown word is non-voiding (the safe direction: it keeps grading), but it must not be silent.
    A disposition nobody registered is a ruling nobody's grader is honouring, and the ledger has
    already demonstrated that drift happening unnoticed."""
    return [(key, r) for key, rulings in sorted((index or {}).items())
            for r in rulings if r.disposition not in RECOGNISED_DISPOSITIONS]


def split_excused(items, held_out, voided, key=None):
    """Split flagged frames into ``(gating, ruled, voided)`` — the ONE place that precedence lives.

    Both gates need it and both had written the same three comprehensions, differing only in which
    list they ran over; a fourth copy is how the two would eventually disagree about what excuses a
    frame. **A HELD-OUT ruling wins when a frame is both**: it STANDS and is merely out of this gate's
    scope, which is the more informative label than "the ruling cannot grade at all"."""
    keyof = key or _key_of
    gating, ruled, void_hits = [], [], []
    for item in items or []:
        k = keyof(item)
        if k in held_out:
            ruled.append(item)
        elif k in voided:
            void_hits.append(item)
        else:
            gating.append(item)
    return gating, ruled, void_hits


def print_ruling_readout(index: dict, voided: dict, *, orphans=(), detail=False) -> None:
    """The **Ruling Index**'s whole readout — voided frames, unregistered words, orphaned entries —
    from ONE call, so the two gates cannot print three sections in two different combinations.

    ``detail`` lists every voided frame; without it only the tally prints. The corpus carries 25
    voided frames whose ledger reasons run to full paragraphs, and both gates print this on every push
    to `main` — the Held-out Ledger's own glossary entry warns that such a section is *"useful only
    while small: past ~a dozen frames it becomes wallpaper, which is the failure mode it exists to
    prevent"*. So a **capture** (rare, deliberate, read closely) lists them; a **diff** (every push)
    prints the tally and points at the file. The verdict block still names any voided frame that
    actually MOVED, which is the actionable subset."""
    if voided:
        by_disposition = {}
        for r in voided.values():
            by_disposition[r.disposition] = by_disposition.get(r.disposition, 0) + 1
        tally = ", ".join(f"{n} {d}" for d, n in sorted(by_disposition.items()))
        print(f"\n  VOIDED ({len(voided)}: {tally}) — the ruling cannot grade these frames; "
              f"out of the agree rate, never gating. Reasons: data/corrections/reviewed.json")
        if detail:
            for key, r in sorted(voided.items()):
                reason = " ".join((r.reason or "").split())
                print(f"    {key:<26} {r.disposition:<14} "
                      f"{reason[:90]}{'…' if len(reason) > 90 else ''}")

    unknown = unrecognised_rulings(index)
    if unknown:
        print(f"\n  ⚠️ UNRECOGNISED DISPOSITION ({len(unknown)}) — non-voiding, so these frames still "
              f"grade; add the word to gates.RECOGNISED_DISPOSITIONS or fix the ledger:")
        for key, r in unknown:
            print(f"    {key}  {r.disposition!r} ({r.source})")

    if orphans:
        print(f"\n  ⚠️ ORPHANED RULING ({len(orphans)}) — these ledger entries match NO committed "
              f"Correction, so they rule on nothing; re-key or delete them:")
        for rkey, entry in orphans:
            print(f"    {rkey:<26} {entry.get('disposition')!r}")


def agree_delta(before: dict, after: dict, *, agrees, moved, voided=(), keep=None) -> dict:
    """The **Agree Delta** — the agree rate on both sides WITH the counts of what moved beside it.

    The aggregate half of the fix `ruling_moves` made per-frame (ADR-TEMP-239 decision 7). Measured:
    re-capturing the baseline moved **three** rows and the headline printed ``230/331 -> 230/331``,
    because one re-ruling flipped a frame disagree->agree and exactly cancelled a held-out
    regression's agree->disagree. Offsetting moves presenting as stillness is the same class of event
    as a quietly shrinking corpus, which `added`/`removed` are surfaced deliberately to prevent.

    **Counts, never a causal decomposition.** A frame can be re-ruled, voided AND moved at once, so no
    point of the delta has a single honest owner; ``+1 reruled, -1 regressed`` would be a confident
    claim this cannot support. This module's history — a mis-keyed baseline, a diff that under-reported
    — says a confidently-wrong instrument is the expensive failure, and a count cannot be
    confidently wrong.

    Both sides are restated against TODAY's voided set, deliberately: the rulings are one corpus, not
    a property of the capture, so restating the baseline is what makes ``230/331 -> 231/313``
    legible rather than an unexplained denominator jump.

    ``agrees(row) -> True | False | None`` (None = the row carries no gradeable ruling) and
    ``moved(before_row, after_row) -> bool`` are the caller's, because the Decision Gate reads
    ``chosen``/``correct`` and the Discrimination Gate reads ``correct_is_top``. ``keep`` is the same
    row filter the reporting diff uses, so every number in one report describes one population."""
    voided = set(voided or ())
    b, a = rows_by_key(before, keep=keep), rows_by_key(after, keep=keep)

    def rate(rows):
        graded = [r for k, r in rows.items() if k not in voided and agrees(r) is not None]
        return sum(1 for r in graded if agrees(r)), len(graded)

    shared = b.keys() & a.keys()
    return {"before": rate(b), "after": rate(a),
            "moved": sum(1 for k in shared if moved(b[k], a[k])),
            "reruled": len(ruling_moves(before, after, keep=keep)),
            "voided": len(voided & (b.keys() | a.keys()))}


def print_agree_delta(delta: dict) -> None:
    """The shared one-line readout. Printed by BOTH gates from one implementation, for the reason
    `frame_key_of` is one function: a second copy drifts, and a re-capture is exactly the moment
    nobody re-reads the printer."""
    if not delta:
        return
    (ba, bn), (aa, an) = delta["before"], delta["after"]
    print(f"\n  agree {ba}/{bn} -> {aa}/{an}  ({delta['moved']} picks moved, "
          f"{delta['reruled']} rulings moved, {delta['voided']} voided)")


# ── the filesystem-facing functions ───────────────────────────────────────────────────────────────
# Everything above is pure so it unit-tests without a filesystem. These read the committed corpus,
# and live here rather than in either gate because BOTH consult the same Ledger — putting them in one
# gate would make the other import its sibling just to read a ruling. They share ONE corpus walk
# (`iter_keyed_fixtures`) for the same reason `frame_key_of` is the single place the key shape is
# built: a second glob that drifted by a field would silently stop seeing frames.

#: Observation keys a corpus fixture may legitimately carry beyond its Correction's own snapshot:
#: ADR-0050's reseeding payload, which is what lets the offline sim replay the board. They change HOW
#: a fixture replays, never WHAT the human ruled — so **Claim Agreement** compares boards modulo them.
#: Five committed fixtures rely on this; a byte-compare reports them as five phantom divergences.
SEEDED_OBS_KEYS = ("own_prizes", "search_begin_input")


def write_json_artifact(path, doc) -> None:
    """Write a gate artifact (a capture, a verdict) as **LF-framed UTF-8 bytes**.

    Both labs write JSON artifacts and both used ``Path.write_text``, which on Windows rewrites every
    ``\\n`` to ``\\r\\n``. `data/decider_lab/baseline.json` and `data/leaf_lab/baseline.json` are
    committed LF, so a re-capture from a Windows box turned a 40-row data change into a 4835-line
    whole-file rewrite — burying the one thing a reviewer of a re-capture needs to see. Dev is on
    Windows and the grader is Linux (CLAUDE.md), so the framing has to be chosen, not inherited.

    Shared rather than fixed twice for this module's own reason: a second implementation drifts, and
    a re-capture is exactly the moment nobody re-reads the writer."""
    from pathlib import Path
    import json as _json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json.dumps(doc, indent=2).encode("utf-8"))


def correction_frame_key(correction) -> str:
    """One Correction's **Frame Key** — ``frame_key_of(*identity_key(c))``, and the ONLY way any
    instrument derives one (ADR-0087 decision 2).

    Split out of `keyed_corrections` so a caller holding a single record cannot be tempted to
    re-assemble the shape by hand, which is exactly how the Decision Gate ended up reading ``seat``
    from a snapshot that has no ``seat`` field. Both gates route through here, so ADR-0072 decision
    4's *one ruling holds a frame out of BOTH gates* is structural rather than a convention."""
    from train.blunder.correction import identity_key
    return frame_key_of(*identity_key(correction))


def keyed_corrections(store=None, *, predicate=None) -> list:
    """**THE Corpus Reader** — every committed Correction, already paired with its **Frame Key**
    (ADR-0087 decisions 1–2, Issue #241). Returns ``[(frame_key, Correction), ...]``.

    Two rules, and they are the same rule twice:

    * **Records are CONSTRUCTED**, via ``load_corrections`` — never walked as raw JSONL. That is what
      inherits ``Correction.from_dict``'s ``agent_build`` backfill, and every future normalisation,
      for both gates at once. The Decision Gate kept its own raw walk and dropped **40** records on a
      falsy ``agent`` — a *recoverable* field, not a missing one — before a row existed, so they
      landed in neither capture and ``added``/``removed`` could never surface them.
    * **The key is DERIVED**, via ``frame_key_of(*identity_key(c))`` — never hand-assembled. The gate
      built its own from raw dict lookups and read ``seat`` off the ``decision`` snapshot, which has
      no ``seat`` field (it is top-level), so every key it produced said seat 0 against a corpus that
      is 201/171. Scope and subject were hardcoded too. Net: **169 of 372 keys correct**, and four of
      the eleven Held-out Ledger rulings unreachable — a frame ruled by a human failing `main` behind
      their back. It drifted undetectably because BOTH sides of a diff shared the same wrong key, so
      the diff stayed self-consistent and nothing ever went red.

    Returning **pairs, not a dict**, is deliberate. A dict silently collapses two Corrections sharing
    a key; today that is measurably zero, but ``load_corrections`` deliberately keeps *conflicts*
    (same identity, different ``correct``/``category`` — what ``find_conflicts`` surfaces), and a
    reader that drops one would commit this issue's own defect at the seam built to remove it. A
    caller wanting a mapping builds one and owns that choice.

    ``predicate`` filters on the CONSTRUCTED record (e.g. ``lambda c: c.obs and c.agent`` for the
    replayable set), so a filter can never again be applied to a field the raw shape had not yet
    normalised."""
    from train.blunder.store import DEFAULT_ROOT, load_corrections

    corrections = load_corrections(store if store is not None else DEFAULT_ROOT)
    return [(correction_frame_key(c), c)
            for c in corrections if predicate is None or predicate(c)]


def iter_keyed_fixtures(fixtures_dir=None):
    """Yield ``(path, fixture, frame_key, Claims)`` per committed fixture declaring a ``frame_key``.

    THE one corpus walk. Declaring a ``frame_key`` is what opts a fixture into everything keyed on
    ADR-0049's identity — the **Held-out Ledger** and **Claim Agreement** alike — so both read the
    corpus through here. A fixture without one is skipped, which is what keeps ADR-0082's back-fill
    incremental and matches `parse_claims`'s own back-compat promise."""
    import json
    from pathlib import Path
    root = Path(fixtures_dir) if fixtures_dir else \
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corrections"
    for path in sorted(root.glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        key = fx.get("frame_key")
        if key:
            yield path, fx, key, parse_claims(fx)


def claim_declares_a_divergence(claim) -> bool:
    """Does this claim DECLARE that it departs from its Correction?

    ADR-0082 decision 2 allows exactly two escapes and no others, both already-shipped ADR-0072
    fields so this adds an invariant rather than a schema:

    * an ``owner`` — a **Held-out Frame**, ruled onto another issue (`dragapult_hammer_over_develop_f32`
      asserts ``[3]`` against a recorded ``[1]``, ruled onto Issue #165);
    * a dated ``why`` — a re-ruling the fixture records itself, with no owner because it is held out of
      nothing; it simply departs (`dp_hold_evolve_until_typed_ready_f35`'s shape).

    An **undated** ``why`` does not clear it, and the date must satisfy `RULED_RE` — the same
    ``YYYY-MM-DD`` shape a held-out claim's ``ruled`` already owes. A claim that cannot be audited
    against the record on a real date is prose, and prose losing a re-ruling is the whole failure
    ADR-0072 named; ``"ruled": "soon"`` would reopen it.

    A non-string ``ruled`` (``true``, a number) is **rejected, never raised on**: a hand-edited fixture
    is exactly where that typo appears, and a gate that crashes on malformed input is a gate that gets
    skipped rather than fixed."""
    if held_out_owner(claim):
        return True
    ruled, why = getattr(claim, "ruled", None), getattr(claim, "why", None)
    return bool(why) and isinstance(ruled, str) and RULED_RE.match(ruled) is not None


def claim_agreement(fixtures_dir=None, store=None) -> list[dict]:
    """**Claim Agreement** (ADR-0082 decision 2) — every committed fixture whose Decision Claim
    departs from its **Correction**'s ``correct`` without declaring it. Empty list = green.

    The Correction is the *ruling of record*: the **Leaf Lab** scores Corrections, not fixtures, so a
    record left wrong keeps feeding bad ranking signal however many fixtures are right. A fixture may
    still depart — but it must say so via `claim_declares_a_divergence`.

    Three findings, each a ``{fixture, frame_key, kind, ...}`` dict:

    * ``no_record``   — the ``frame_key`` resolves to no committed Correction. A dangling join reads
      exactly like a fixture with nothing to disagree with, so silence here would defeat the gate.
    * ``obs_mismatch`` — the boards differ beyond `SEEDED_OBS_KEYS`. ``correct`` is a list of positional
      option indices, so across two different boards it is not comparable and the claim is *not*
      compared. Reported **regardless of the escapes**: a declared re-ruling excuses a different
      *ruling*, never an unsound *join*.
    * ``disagreement`` — the claim and the record name different picks, undeclared.

    Opting in is `iter_keyed_fixtures`' business: a fixture with no ``frame_key`` has no join, and
    deriving one from the loose ``episode``+``frame`` pair would be guessing at ADR-0049's identity
    (the Scope's *subject*, not the Anchor frame). Several fixtures may share one key — legal and
    load-bearing — so each is judged independently."""
    by_key = dict(keyed_corrections(store))     # THE Corpus Reader; last wins, as this join always did

    found: list[dict] = []
    for path, fx, key, claims in iter_keyed_fixtures(fixtures_dir):
        claim = claims.decision
        if claim is None:                    # a fixture asserting only lane claims has no pick to check
            continue
        rec = by_key.get(key)
        if rec is None:
            found.append({"fixture": path.name, "frame_key": key, "kind": "no_record",
                          "claim": list(claim.correct), "record": None})
            continue
        mismatch = _obs_mismatch_keys(fx.get("obs"), rec.obs)
        if mismatch:
            found.append({"fixture": path.name, "frame_key": key, "kind": "obs_mismatch",
                          "claim": list(claim.correct), "record": list(rec.correct or []),
                          "keys": mismatch})
            continue
        if sorted(claim.correct) != sorted(rec.correct or []) and not claim_declares_a_divergence(claim):
            found.append({"fixture": path.name, "frame_key": key, "kind": "disagreement",
                          "claim": list(claim.correct), "record": list(rec.correct or [])})
    return found


def _obs_mismatch_keys(fixture_obs, record_obs) -> list:
    """Top-level observation keys on which the two boards differ, ignoring `SEEDED_OBS_KEYS`.

    Top-level is deliberate: a deeper diff would report the same board twice over (the seeding payload
    also perturbs nested prize counts), and the question here is only *is this the same board* — a
    binary the option indices depend on."""
    if fixture_obs is None or record_obs is None:
        return []
    keys = (set(fixture_obs) | set(record_obs)) - set(SEEDED_OBS_KEYS)
    return sorted(k for k in keys if fixture_obs.get(k) != record_obs.get(k))


def held_out_frames(fixtures_dir=None) -> dict:
    """The **Held-out Ledger**: ``{frame key: owner}`` over the committed corpus fixtures.

    A fixture opts in by declaring ``frame_key`` (the Correction's ``identity_key``, the same shape
    both gates key on) and an ``owner`` on its Decision Claim. The leaf verdict is a whole-frame
    property rather than a per-lane one, so it is the DECISION claim's owner that holds a frame out
    of the Discrimination Gate; lane claims stay independently gated (decision 4). Deleting the owner
    returns the frame to gating."""
    out = {}
    for _path, _fx, key, claims in iter_keyed_fixtures(fixtures_dir):
        owner = held_out_owner(claims.decision) if claims.decision else None
        if owner:
            out[key] = owner
    return out


def ruling_index(store=None, *, reviewed_path=None, fixtures_dir=None) -> dict:
    """**THE Ruling Index** — ``{frame key: (Ruling, ...)}`` over every store a ruling can live in
    (ADR-TEMP-239 decision 2, Issue #239). The ONE query answering *"has this frame been ruled, and
    where?"*.

    It exists because a frame could be ruled four different ways and still read as unreviewed.
    `82749168-38` sits in `reviewed.json` AND ADR-0085 decision 7 and was triaged Tier A;
    `81905522-75` sat in ADR-0085 decision 7 AND the snipe sweep's private ``RECORDED_MISSES``,
    never in `reviewed.json`, and was triaged Tier C — *"never reviewed"*. Same ruling, same ADR,
    same permanence, different tier, purely by which store happened to hold it.

    **Read-only. No Correction record is rewritten.** Putting the refutation ON the record (a
    ``refuted`` flag, a ``superseded_by``) was rejected for now: it makes a record mutable under the
    C2 provenance contract, needs a migration of committed JSONL, and lands on ADR-0082's Claim
    Agreement. If Issue #229 forces a schema change anyway, this absorbs it as one more source rather
    than becoming a rewrite of every grader.

    **The join is DERIVED, inside the one corpus walk.** `reviewed.json` keys by ADR-0049's Scope
    subject (`review_key`: ``<ep>-<frame>`` / ``<ep>-t<turn>s<seat>`` / ``<ep>-m<seat>``); the gates
    key by **Frame Key** (`correction_frame_key`: ``<ep>|<seat>|<scope>|<subject>``). Both come off the
    same `Correction` and NEITHER derives from the other, so the walk is the only honest join point —
    translating between the two string shapes anywhere else is the hand-built key ADR-0087 decision 2
    forbids, and the one that cost the Decision Gate 203 of its 372 keys.

    Two sources, not three: the snipe sweep's ``RECORDED_MISSES`` is RETIRED into these (decision 5)
    rather than read as a fourth store — reading it would make this module import from
    `tools/train/probes/`, inverting the layering, to consult a store with no disposition vocabulary
    at all.

    Stores are injectable so the whole index tests against a ``tmp_path`` corpus, the same seam
    `claim_agreement` is asserted at."""
    from train.blunder.reviewed import load_reviewed, review_key

    reviewed = load_reviewed(reviewed_path) if reviewed_path is not None else load_reviewed()

    out: dict = {}
    for key, c in keyed_corrections(store):
        entry = reviewed.get(review_key(c))
        if entry:
            out.setdefault(key, []).append(
                Ruling(disposition=str(entry.get("disposition") or ""), source="reviewed",
                       reason=str(entry.get("reason") or "")))

    for key, owner in held_out_frames(fixtures_dir).items():
        out.setdefault(key, []).append(
            Ruling(disposition="held_out", source="held_out",
                   reason=f"ruled onto {owner}", owner=owner))

    # Voiding first, so `voiding_ruling` reads the strongest ruling without re-sorting, and a readout
    # that prints only the first entry prints the one that changed the frame's fate.
    return {k: tuple(sorted(v, key=lambda r: not voids_the_label(r))) for k, v in out.items()}


def orphan_rulings(store=None, *, reviewed_path=None) -> list:
    """``[(review_key, entry), ...]`` for every `reviewed.json` entry matching NO committed
    Correction — the **Ruling Index**'s detachment guard.

    `ruling_index` walks the CORPUS and looks each record up in the ledger, so an entry the corpus
    cannot reach never enters the index and would be invisible in both directions: it rules on
    nothing, and nothing reports that it rules on nothing. That is the same dangling-join failure
    `claim_agreement`'s ``no_record`` finding exists to surface one store over, and
    `held_out_frames` is asserted against for the other — a ruling detached from its record reads
    exactly like a frame nobody ruled.

    Measured 2026-07-31: **two** entries are orphaned, and one of them (`86091435-119`) is a
    ``refuted`` — a human refutation voiding nothing, silently, which is precisely the class of
    defect Issue #239 was opened about."""
    from train.blunder.reviewed import load_reviewed, review_key

    reviewed = load_reviewed(reviewed_path) if reviewed_path is not None else load_reviewed()
    reachable = {review_key(c) for _key, c in keyed_corrections(store)}
    return [(k, entry) for k, entry in sorted(reviewed.items()) if k not in reachable]


def picks_as_set(pick):
    """A pick compared as a SET, not a sequence.

    Multi-pick contexts (`DISCARD` asks for N cards) legitimately return several indices, and their
    ORDER is not a decision — the engine applies the whole set. Comparing sequences would report a
    reordered multi-pick as a movement, which is a false positive in the one direction the Decision
    Gate must never produce."""
    return None if pick is None else frozenset(pick)


def satisfies_human(chosen, correct) -> bool:
    """Does ``chosen`` satisfy the Correction's ruling — the ONE predicate both readings key on.

    **A Correction's ``correct`` is a CONSTRAINT, not the whole legal answer** (ADR-0085 Amendment J,
    ruling the question ADR-0085 Amendment I left open). It names *the card the ruling was about*,
    which is exactly what ADR-0082's Claim vocabulary records; a multi-pick select meanwhile returns
    **every** index the engine requires. So the two vocabularies are not the same shape, and equality
    between them is the wrong test:

        DISCARD, `correct: [2]`, agent picks `[2, 3]`
            equality  -> DISAGREE   (and the capture read 1/12 on `DISCARD` for exactly this reason,
                                     which is a VOCABULARY MISMATCH, not a defect)
            this test -> AGREE      (the ruled card *was* discarded; index 3 is the engine's other
                                     required slot, which the human never ruled on either way)

    Satisfaction is therefore ``correct ⊆ chosen``. On a single-pick context both sides are one
    index, so it degenerates to equality and nothing changes — which is why the 220 single-pick
    agreements are untouched by this.

    The alternative ruling — rewrite those Corrections to record the full answer — was rejected: it
    would put indices into a human ruling that the human never ruled on, destroying the one thing
    ``correct`` is for. Read the record correctly rather than editing the record.

    Three cases, each load-bearing:

    * ``chosen is None`` — an unreplayable frame satisfies nothing. It must not read as agreement.
    * ``correct is None`` — no ruling was recorded, so nothing can be satisfied. Callers report these
      as ``UNLABELLED`` rather than as disagreement.
    * ``correct == []`` — a recorded **DECLINE**: the ruling is *"take none of these"*, satisfied
      only by an empty pick. Subset is WRONG here and dangerously so — the empty set is a subset of
      everything, so reading a DECLINE through ``⊆`` would make every frame vacuously agree. **Ten**
      such frames sit in the corpus, all ``turn`` scope (eight at ``MAIN``, one ``TO_HAND``, one
      ``SETUP_BENCH_POKEMON``), and `86088989|0|turn|0` is genuinely satisfied — the agent
      declines too. They are rulings, so they stay labelled and stay gated; Issue #229 owns whether
      the *writer* should keep rejecting the shape the corpus already contains.

      ⚠️ This paragraph previously said *eleven*, and named that frame `86088989|0|decision|3`.
      Both were readings of the **mis-keyed** Decision Gate baseline (Issue #241): its keys were
      built by hand with ``seat`` read off a snapshot that has no ``seat`` field and ``scope``
      hardcoded to ``decision``, and its eleventh DECLINE row was `85709280`, whose ``correct`` had
      since been re-ruled ``[] -> [0]`` in `b6d7483` — a **Ruling Move** no instrument could report
      until `ruling_moves` existed. A wrong keyspace propagating into an ADR-backed docstring is
      the clearest argument for `correction_frame_key` being the only derivation.
    """
    if chosen is None or correct is None:
        return False
    if not correct:                       # a recorded DECLINE — exact, never subset
        return not chosen
    return picks_as_set(correct) <= picks_as_set(chosen)


def rows_by_key(rpt: dict, *, keep=None) -> dict:
    """A capture's rows indexed by **Frame Key** — the one place a capture is turned into a lookup.

    Both diffs and `ruling_moves` need this, and all three had written their own closure. That is
    the shape this module keeps having to remove: three copies differing only by a filter clause,
    which is how `ruling_moves` came to index a different row population than the `leaf_lab_diff`
    it reports beside. ``keep`` is that filter, passed in rather than baked in.

    A row with no key is dropped: it cannot be diffed, and keeping it would collide every such row
    onto a single ``None`` bucket."""
    return {r["key"]: r for r in (rpt.get("rows") or [])
            if r.get("key") and (keep is None or keep(r))}


def _scorable(row) -> bool:
    """The Leaf Lab's row filter — an unscorable frame has no verdict to compare."""
    return not row.get("unscorable")


def ruling_moves(before: dict, after: dict, *, keep=None) -> list:
    """Every frame present in BOTH captures whose **Correction**'s ``correct`` changed — the human
    re-ruled it (**Ruling Move**, ADR-0087 decision 7). ``[{key, before, after}, ...]``.

    Emitted **independently of whether the agent's pick moved**, and that independence IS the fix.
    Both diffs emit a verdict row only on a moved pick, so a frame the agent plays identically whose
    ruling was re-written produces *no row at all* — while its verdict silently flips. Measured:
    ``85709280`` went ``[] -> [0]`` in ``b6d7483`` (ADR-0081 Amendment D) and moved the agree rate
    230 -> 231 with no decision changed. ``added``/``removed`` cannot see it either, because the frame
    is on both sides; it is the same *"a thing that moved that the instrument cannot report"* family
    as Issue #239.

    It sits beside ``added``/``removed`` because it is the same idea one level in — those report a
    frame appearing or leaving, this reports the *ruling about* a frame moving — and the module's
    doctrine is that a corpus-shape move must never read as a quiet green.

    **It never gates.** A re-ruling is a deliberate human act, not an agent regression, so
    `decision_gate_verdict` and `discrimination_gate_verdict` do not consult it.

    Shared by both diffs for `frame_key_of`'s reason: `leaf_lab_diff` compares ``correct_is_top``,
    which is computed FROM ``correct``, so it carries the identical blindness, and a second
    implementation would drift. Normalised by `picks_as_set` — the same predicate the verdict uses,
    so re-ordering ``correct`` is not a re-ruling and the two cannot form different ideas of "moved".

    ``keep`` must be the SAME row filter the diff reporting this uses, so the two numbers printed
    side by side describe one population: `leaf_lab_diff` compares only scorable rows, and a
    ``ruling_moves`` drawn from all of them would report frames its own ``compared`` count excludes.

    A ``None`` on one side and a ruling on the other counts as a move: the frame gained or lost its
    ruling, which changes what the gate can adjudicate there — an ``UNLABELLED`` frame becoming
    gateable is exactly as worth reporting as a ruling being rewritten.
    """
    b, a = rows_by_key(before, keep=keep), rows_by_key(after, keep=keep)
    moved = []
    for k in sorted(b.keys() & a.keys()):
        was, now = b[k].get("correct"), a[k].get("correct")
        if was is None and now is None:
            continue
        if was is None or now is None or picks_as_set(was) != picks_as_set(now):
            moved.append({"key": k, "before": was, "after": now})
    return moved


def print_ruling_moves(moves) -> None:
    """The shared readout, so the two gates cannot describe a **Ruling Move** differently."""
    if not moves:
        return
    print(f"\n  ⚠️ RULING MOVED ({len(moves)}) — the human re-ruled these frames; reported, never gating:")
    for m in moves:
        print(f"    {m['key']}  correct {m['before']} -> {m['after']}")


def decider_lab_diff(before: dict, after: dict, *, voided=()) -> dict:
    """Per-frame DECISION movement between two Decider Lab captures, classified against the human.

    The Decision Gate's comparison after ADR-0085 Amendment I. It replaces the sweeps' live
    kill-switch-OFF arm, which measured *"the equation versus the rungs it replaced"* — a question
    that stops existing the moment those rungs are DELETED. Every decider swap has now deleted its
    pile (`baseline_promote` holds **zero** rungs, `baseline_energy` 3 of 22, `baseline_evolution` 2
    of 6, `baseline_snipe` 3 counter rungs of 9), so all four sweeps were comparing the shipped agent
    against an empty scorer whose argmax is option index. Measured: `evolve_decider_sweep` reported
    `4 FIX, 0 REGRESSION` and `snipe_decider_sweep` `12 FIX, 0 REGRESSION` — **a gate that can only
    ever report FIX cannot report the one thing ADR-0072 built it for.**

    So the reference becomes a RECORDED baseline, exactly as the Discrimination Gate has always used
    one, and the question becomes *"did this build regress against the last blessed build?"* — which
    is a different question from the swap-moment one, and the honest thing to say is that this
    REPLACES the transition instrument rather than repairing it.

    Rows match on the stable ``key`` (`frame_key_of`). Frames on only one side are surfaced
    (``added`` / ``removed``) rather than skipped, so a baseline taken against a different corpus
    shape is visible instead of quietly shrinking the gated set.

    Direction is judged by ``satisfies_human`` (``correct ⊆ chosen``, ADR-0085 Amendment J), NOT by
    equality — the same predicate the capture's agree rate reports through, so the gate and the
    readout cannot drift into two different ideas of "matches the human".

    Verdicts, per frame whose ``chosen`` moved:
      ``REGRESSION``  the baseline satisfied the human's ``correct`` and this build does not
      ``FIX``        this build satisfies it and the baseline did not
      ``NEUTRAL``    the ruling does not separate the two — both satisfy it, or both miss it. A real
                     change, but not one the corpus adjudicates.
      ``UNLABELLED`` the frame carries no ``correct``, so no direction can be claimed

    ``voided`` frames are still classified and still reported — only `decision_gate_verdict` and the
    **Agree Delta** exclude them, so a voided ``REGRESSION`` reads as the visible non-event it is
    rather than vanishing.
    """
    norm = picks_as_set

    b, a = rows_by_key(before), rows_by_key(after)
    rows = []
    for k in sorted(b.keys() & a.keys()):
        was, now = b[k].get("chosen"), a[k].get("chosen")
        if norm(was) == norm(now):
            continue
        correct = a[k].get("correct")
        if correct is None:
            verdict = "UNLABELLED"
        elif satisfies_human(now, correct) and not satisfies_human(was, correct):
            verdict = "FIX"
        elif satisfies_human(was, correct) and not satisfies_human(now, correct):
            verdict = "REGRESSION"
        else:
            verdict = "NEUTRAL"
        rows.append({"key": k, "agent": a[k].get("agent"), "context": a[k].get("context"),
                     "before": was, "after": now, "correct": correct, "verdict": verdict})
    return {"rows": rows, "compared": len(b.keys() & a.keys()),
            "added": sorted(a.keys() - b.keys()), "removed": sorted(b.keys() - a.keys()),
            "ruling_moves": ruling_moves(before, after),
            "agree_delta": agree_delta(
                before, after, voided=voided,
                # `satisfies_human` is the SAME predicate the verdicts above key on, deliberately: the
                # gate and its readout must not form two ideas of "matches the human". None = the row
                # carries no gradeable ruling (unlabelled, or unreplayable so `chosen` is null).
                agrees=lambda r: (None if r.get("correct") is None or r.get("chosen") is None
                                  else satisfies_human(r["chosen"], r["correct"])),
                moved=lambda x, y: norm(x.get("chosen")) != norm(y.get("chosen")))}
