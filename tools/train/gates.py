"""The two deterministic merge gates a mid-build decider swap owes (ADR-0072, #167).

#136 standing directive 6 used to grade every decider swap on a paired A/B win-rate test. Phase 1b
measured what that costs: **−1.17 pp, 95% CI [−4.59, +2.25], 0 crashes / 2400 games** — and pooled
over 4800 games, −1.06 pp, CI [−3.90, +1.78]. The run demonstrated neither a regression nor a
non-regression, and no affordable run could: clearing `CI-lo >= −1%` near a zero delta needs ~28,000
games per phase, and even then `delta >= 0` is a coin flip on a neutral swap. A mid-build swap is not
trying to raise win rate — it makes ONE axis correct in ONE currency so #165 and #145 can compose the
axes — so grading it that way measures it through the weakest consumer it will ever have.

Merit therefore lives here, in two instruments that answer **exactly** rather than statistically:

* **Decision Gate** — the phase's `probes/*_decider_sweep.py`: zero unruled ``REGRESSION`` frames.
  ADR-0069 §8's protocol, promoted from convention to a gate.
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

EVOLVE_LANE: Lane = ((OPTION_TYPE_EVOLVE, None),)
ATTACH_LANE: Lane = ((OPTION_TYPE_ATTACH, None),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_ATTACH_FROM))

#: A held-out claim must name its owner as an issue reference — the shape CI can check offline.
#: Whether that issue is still OPEN cannot be checked here (the suite is offline, CLAUDE.md) and
#: belongs on the phase checklist.
OWNER_RE = re.compile(r"^#\d+$")

#: A held-out claim also records WHEN it was ruled, so a stale ruling is visible as an old date
#: rather than as undated prose.
RULED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def option_slot(option: dict) -> tuple | None:
    """The board **slot** an option targets — ``(inPlayArea, inPlayIndex)``, falling back to
    ``(area, index)`` — or None when it targets no slot at all (END, YES/NO, …).

    Comparison is by slot and **never** by raw option index: two Dreepy->Drakloak evolves differ only
    in which body they evolve, and the index says nothing about which one
    (`evolve_decider_sweep.py`, ADR-0069 §8). Both decider sweeps resolved this themselves; one
    implementation here is what keeps them from drifting apart."""
    if option.get("inPlayArea") is not None:
        return (option.get("inPlayArea"), option.get("inPlayIndex"))
    if option.get("area") is not None:
        return (option.get("area"), option.get("index"))
    return None


def in_lane(option: dict, lane: Lane, select_context=None) -> bool:
    """Is ``option`` a member of ``lane`` under ``select_context``? A member whose required context
    is None matches any context; otherwise the frame's context must equal it."""
    t = option.get("type")
    return any(t == want_type and (want_ctx is None or want_ctx == select_context)
               for want_type, want_ctx in lane)


def lane_slots(indices, options, *, lane: Lane, select_context=None) -> set:
    """The slots ``indices`` resolve to **within** ``lane`` (options outside the lane, and lane
    options that target no slot, contribute nothing)."""
    out = set()
    for i in indices or []:
        if 0 <= i < len(options) and in_lane(options[i], lane, select_context):
            slot = option_slot(options[i])
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


def leaf_lab_diff(before: dict, after: dict) -> dict:
    """Per-frame verdict movement between two Leaf Lab captures.

    Rows are matched on their stable ``key`` (the Correction's ``identity_key``). Keying on
    ``episode_id`` alone silently merged frames from one episode — it collapsed a real 276-row diff
    to 221 — and an under-reporting gate is the precise failure mode this exists to prevent. Frames
    present on only one side are surfaced (``added``/``removed``) rather than quietly skipped, so a
    capture taken against a different corpus shape is visible."""
    def index(rpt):
        return {r["key"]: r for r in (rpt.get("rows") or []) if not r.get("unscorable")}

    b, a = index(before), index(after)
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
            "compared": len(shared)}


def discrimination_gate_verdict(diff: dict, *, held_out: dict) -> bool:
    """PASS iff no frame degraded ``OK -> MISS`` without a ruling.

    Improvements never block, and the aggregate metrics (SOLE-top / shared-top / avg top-tie) are not
    consulted at all — on 1b they moved the *good* way while six frames broke."""
    return all(f["key"] in held_out for f in diff.get("ok_to_miss") or [])


def decision_gate_verdict(rows, *, held_out: dict) -> bool:
    """PASS iff no frame carries an unruled ``REGRESSION``. ``FIX`` and ``DIVERGENT`` never block —
    the sweep puts every flip in front of the human, and only a regression they have not ruled is a
    blocker."""
    return all(r["key"] in held_out
               for r in rows or [] if r.get("verdict") == "REGRESSION")


def frame_key_of(episode_id, seat, scope, subject) -> str:
    """The flat string form of a Correction's ``identity_key`` — ``episode|seat|scope|subject``.

    THE one place that shape is built. Both gates key on it and one ruling must hold a frame out of
    either, so a second implementation that drifted by a field would silently stop matching. The
    Leaf Lab passes the values straight off a Correction; the sweeps read them off the raw record."""
    return "|".join("" if p is None else str(p) for p in (episode_id, seat, scope, subject))


def print_gate_report(title, *, gating, ruled, held_out, total, rule, line) -> bool:
    """Print one gate's verdict block and return whether it PASSED — shared by both gates so their
    reports cannot drift in shape or in what they claim.

    ``ruled`` frames are printed in an always-visible ``HELD OUT`` section and excluded from the
    verdict (ADR-0072 decision 4): a re-ruling is a state the gate reads, and a frame broken for
    three phases must not become scenery. ``line(item)`` renders one row."""
    print(f"\n=== {title} ===")
    for item in gating:
        print(f"  {line(item)}")
    if ruled:
        print(f"\n  HELD OUT ({len(ruled)}) — reported, not gated:")
        for item in ruled:
            print(f"    {line(item)}  owner={held_out.get(_key_of(item))}")
    print(f"\n  gated on {total - len(ruled)} frame(s), held out {len(ruled)}")
    passed = not gating
    print(f"GATE: {'PASS' if passed else 'FAIL'}  "
          f"(rule: {rule}; {len(gating)} unruled, {len(ruled)} ruled)")
    return passed


def _key_of(item) -> str:
    return item["key"] if isinstance(item, dict) else str(item)


def held_out_map(claims_by_key: dict) -> dict:
    """``{frame key: owner}`` for every claim that has been ruled onto an owner — the Held-out
    Ledger both gates consult."""
    return {k: held_out_owner(c) for k, c in claims_by_key.items() if held_out_owner(c)}


# ── the one I/O function in this module ───────────────────────────────────────────────────────────
# Everything above is pure so it unit-tests without a filesystem. This reads the committed corpus,
# and lives here rather than in either gate because BOTH consult the same Ledger — putting it in one
# gate would make the other import its sibling just to read a ruling.

def held_out_frames(fixtures_dir=None) -> dict:
    """The **Held-out Ledger**: ``{frame key: owner}`` over the committed corpus fixtures.

    A fixture opts in by declaring ``frame_key`` (the Correction's ``identity_key``, the same shape
    both gates key on) and an ``owner`` on its Decision Claim. The leaf verdict is a whole-frame
    property rather than a per-lane one, so it is the DECISION claim's owner that holds a frame out
    of the Discrimination Gate; lane claims stay independently gated (decision 4). Deleting the owner
    returns the frame to gating."""
    import json
    from pathlib import Path
    root = Path(fixtures_dir) if fixtures_dir else \
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corrections"
    out = {}
    for path in sorted(root.glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        key = fx.get("frame_key")
        if not key:
            continue
        claims = parse_claims(fx)
        owner = held_out_owner(claims.decision) if claims.decision else None
        if owner:
            out[key] = owner
    return out
