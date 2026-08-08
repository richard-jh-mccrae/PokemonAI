"""The two deterministic merge gates a decider swap owes — Decision and Discrimination (ADR-0072).

Both are per-frame, never aggregate: on the swap that motivated them the aggregate metrics moved the
GOOD way while six frames broke. Everything above the "filesystem-facing" divider is a pure function
over plain dicts, and importing the engine here would cost the gates their DLL-free unit suite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: ``(option_type, required_select_context | None)`` members — the option shapes one Axis Claim
#: ranks within, as DATA rather than a call-site special case.
Lane = tuple

#: Written literally, never imported: `import cg.api` MAPS THE NATIVE LIBRARY and this module must
#: stay loadable with no DLL. Pinned to the enums by `test_lane_constants_match_the_engine_enums`.
OPTION_TYPE_EVOLVE = 9                              # cg.api.OptionType.EVOLVE
OPTION_TYPE_ATTACH = 8                              # cg.api.OptionType.ATTACH
OPTION_TYPE_CARD = 3                                # cg.api.OptionType.CARD
SELECT_CONTEXT_ATTACH_FROM = 21                     # cg.api.SelectContext.ATTACH_FROM
SELECT_CONTEXT_SWITCH = 3                           # cg.api.SelectContext.SWITCH
SELECT_CONTEXT_TO_ACTIVE = 4                        # cg.api.SelectContext.TO_ACTIVE

EVOLVE_LANE: Lane = ((OPTION_TYPE_EVOLVE, None),)
ATTACH_LANE: Lane = ((OPTION_TYPE_ATTACH, None),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_ATTACH_FROM))
#: "Promote THIS body over that one" (ADR-0100 §12). Both the forced promote and the retreat
#: destination pose an `OptionType.CARD`, so the lane is that type under either context.
PROMOTE_LANE: Lane = ((OPTION_TYPE_CARD, SELECT_CONTEXT_SWITCH),
                      (OPTION_TYPE_CARD, SELECT_CONTEXT_TO_ACTIVE))

OPTION_TYPE_PLAY = 7                                # cg.api.OptionType.PLAY
SELECT_CONTEXT_SETUP_BENCH = 2                      # cg.api.SelectContext.SETUP_BENCH_POKEMON
SELECT_CONTEXT_TO_BENCH = 5                         # cg.api.SelectContext.TO_BENCH
AREA_HAND = 2                                       # cg.api.AreaType.HAND

#: Every way a body reaches MY Bench, as one decision (ADR-0086): a mid-game `PLAY` from hand, the
#: pregame placement, and a fetch straight onto the Bench.
DEPLOY_LANE: Lane = ((OPTION_TYPE_PLAY, None),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_SETUP_BENCH),
                     (OPTION_TYPE_CARD, SELECT_CONTEXT_TO_BENCH))

#: Whether the named issue is still OPEN cannot be checked here — the suite is offline.
OWNER_RE = re.compile(r"^#\d+$")

RULED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hand_card_id(option: dict, frame: dict | None):
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
    """The identity an option targets: a board slot ``(inPlayArea, inPlayIndex)``; else — given ``frame``
    — ``("card", cardId)`` for a hand card; else ``(area, index)``; else None. Never the raw index."""
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
    t = option.get("type")
    return any(t == want_type and (want_ctx is None or want_ctx == select_context)
               for want_type, want_ctx in lane)


def lane_slots(indices, options, *, lane: Lane, select_context=None, frame: dict | None = None) -> set:
    out = set()
    for i in indices or []:
        if 0 <= i < len(options) and in_lane(options[i], lane, select_context):
            slot = option_slot(options[i], frame)
            if slot is not None:
                out.add(slot)
    return out


@dataclass(frozen=True)
class DecisionClaim:
    """*Given the whole board, the agent picks this.* The cross-lane, end-to-end assertion."""
    correct: list
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class AxisClaim:
    """*Within ONE lane, this slot outranks those.* An ORDERING claim, never a score claim: ordering
    survives a currency re-banding, cross-lane scores do not. It cannot rescue a cross-lane defect."""
    lane: Lane
    prefer: tuple
    over: list
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class EndorsementClaim:
    """*This slot is (or is not) taken at all*, against ``score > 0`` — what an ordering cannot say when
    a lane holds one option. Zero is a STRUCTURAL boundary, so it survives a re-banding as ordering does."""
    lane: Lane
    slot: tuple
    endorsed: bool
    owner: str | None = None
    ruled: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class Claims:
    """What one corpus fixture asserts. Held-out status is per CLAIM, not per fixture."""
    decision: DecisionClaim | None = None
    axis: list = field(default_factory=list)
    endorsement: list = field(default_factory=list)

    def all_claims(self) -> list:
        return ([self.decision] if self.decision else []) + list(self.axis) + list(self.endorsement)


def _lane_from(spec) -> Lane:
    if isinstance(spec, int):
        return ((spec, None),)
    return tuple((int(t), c) for t, c in spec)


def parse_claims(fixture: dict) -> Claims:
    """Read a fixture's ``claims`` block; with no block, a Decision Claim synthesised from ``correct``."""
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
    """The issue a claim is ruled onto, or None when it GATES. Deleting ``owner`` returns it to gating."""
    return getattr(claim, "owner", None) or None


def evaluate_decision_claim(claim: DecisionClaim, *, chosen) -> bool:
    return sorted(claim.correct) == sorted(chosen or [])


def evaluate_axis_claim(claim: AxisClaim, *, options, scores, select_context=None) -> bool:
    """Does ``prefer`` STRICTLY outrank every slot in ``over``, within the claim's lane? Strictly: the
    argmax breaks ties by option order, so a shared top would let the wrong body be picked."""
    best = _lane_best(claim, options, scores, select_context)
    if claim.prefer not in best:
        return False
    return all(best[claim.prefer] > best[rival] for rival in claim.over if rival in best)


def _lane_best(claim, options, scores, select_context):
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
    """Does ``slot`` clear the endorsement floor (``score > 0``), and does that match the claim? **None**
    when the slot is not on the menu — unprovable, never vacuously true."""
    best = _lane_best(claim, options, scores, select_context)
    if claim.slot not in best:
        return None
    return (best[claim.slot] > 0) is claim.endorsed


def leaf_lab_diff(before: dict, after: dict, *, voided=()) -> dict:
    """Per-frame verdict movement between two Leaf Lab captures, matched on ``key`` (``episode_id`` alone
    is not unique). ``voided`` frames are still compared and reported; only the verdict excludes them."""
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
    # SAME row filter as `compared` above, so the two numbers in one report describe one
    # population — a ruling_moves drawn from all rows would name frames `compared` excludes.
    moves = ruling_moves(before, after, keep=_scorable)
    moved_keys = {m["key"] for m in moves}
    return {"ok_to_miss": ok_to_miss, "miss_to_ok": miss_to_ok,
            "added": sorted(a.keys() - b.keys()), "removed": sorted(b.keys() - a.keys()),
            "compared": len(shared),
            "ruling_moves": moves,
            # A PARTITION of `ok_to_miss` holding its own entries, not a filtered copy and not a
            # subtraction: a moved ruling grades the two halves under two oracles (ADR-0110).
            "stale_baseline": [f for f in ok_to_miss if f["key"] in moved_keys],
            "agree_delta": agree_delta(
                before, after, keep=_scorable, voided=voided,
                # The Leaf Lab's ruling is `correct_is_top`; an unscorable row is already filtered out
                # by `keep`, so every surviving row is gradeable.
                agrees=lambda r: bool(r.get("correct_is_top")),
                moved=lambda x, y: bool(x.get("correct_is_top")) != bool(y.get("correct_is_top")))}


def discrimination_gate_verdict(diff: dict, *, held_out: dict, voided=()) -> bool:
    """PASS iff no frame degraded ``OK -> MISS`` without a ruling. Aggregate metrics are never consulted.
    ``held_out`` and ``voided`` excuse a frame; ``stale_baseline`` deliberately does NOT (ADR-0110)."""
    excused = set(held_out) | set(voided or ())
    return all(f["key"] in excused for f in diff.get("ok_to_miss") or [])


def decision_gate_verdict(rows, *, held_out: dict, voided=()) -> bool:
    """PASS iff no frame carries an unruled ``REGRESSION``. ``FIX`` and ``DIVERGENT`` never block, and a
    ``REGRESSION`` on a **voided** frame is reported without blocking (ADR-0088 decision 4)."""
    excused = set(held_out) | set(voided or ())
    return all(r["key"] in excused
               for r in rows or [] if r.get("verdict") == "REGRESSION")


def frame_key_of(episode_id, seat, scope, subject) -> str:
    """``episode|seat|scope|subject`` — THE one place that shape is built. Both gates key on it, so a
    second implementation drifting by a field would silently stop matching."""
    return "|".join("" if p is None else str(p) for p in (episode_id, seat, scope, subject))


def print_gate_report(title, *, gating, ruled, held_out, total, rule, line,
                      voided=(), voided_by=None) -> bool:
    """One gate's verdict block, shared so the two cannot drift. ``ruled`` and ``voided`` print separately."""
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
    return {k: held_out_owner(c) for k, c in claims_by_key.items() if held_out_owner(c)}


#: A ruling the human recorded, wherever it was recorded. `source` names the store, so the **Ruling
#: Index** doubles as the "where is this ruled?" register rather than a bare skip-list.
@dataclass(frozen=True)
class Ruling:
    disposition: str
    source: str                       # "reviewed" | "held_out"
    reason: str = ""
    owner: str | None = None          # the Held-out Ledger's field; `reviewed.json` carries none


#: Dispositions that VOID a label: ``refuted`` (the ruling is DISOWNED) and ``transposition`` (it
#: STANDS but names one of an indistinguishable set). Both leave the denominator and stop gating.
VOIDING_DISPOSITIONS = frozenset({"refuted", "transposition"})

#: Every disposition the index UNDERSTANDS. Anything outside it is non-voiding and reported LOUDLY
#: (`unrecognised_rulings`) rather than swallowed.
RECOGNISED_DISPOSITIONS = VOIDING_DISPOSITIONS | frozenset({
    "covered", "deferred", "deferred-multi-turn", "fixed", "held_out"})


def voiding_disposition(disposition: str | None) -> bool:
    return disposition in VOIDING_DISPOSITIONS


def voids_the_label(ruling) -> bool:
    """Does this **Ruling** void the human's label — the ONE predicate every grader keys on. Never branch
    on ``ruling.disposition`` at a call site: the vocabulary grows (ADR-0087)."""
    return voiding_disposition(getattr(ruling, "disposition", None))


def voiding_ruling(rulings):
    """The **Ruling** that voids a frame, or None. **Any voiding source wins**; a weaker one must not mask it."""
    for r in rulings or ():
        if voids_the_label(r):
            return r
    return None


def voided_frames(index: dict) -> dict:
    out = {}
    for key, rulings in (index or {}).items():
        hit = voiding_ruling(rulings)
        if hit is not None:
            out[key] = hit
    return out


def unrecognised_rulings(index: dict) -> list:
    """Dispositions outside `RECOGNISED_DISPOSITIONS`. Non-voiding (it keeps grading) but never silent."""
    return [(key, r) for key, rulings in sorted((index or {}).items())
            for r in rulings if r.disposition not in RECOGNISED_DISPOSITIONS]


def split_excused(items, held_out, voided, key=None):
    """Split flagged frames into ``(gating, ruled, voided)`` — the ONE place that precedence lives. **A
    HELD-OUT ruling wins when a frame is both**: it STANDS and is merely out of this gate's scope."""
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
    """The **Ruling Index**'s whole readout from ONE call. ``detail`` lists the voided frames, else a tally."""
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
    """The agree rate on both sides with the counts of what moved beside it. Counts, never a causal
    decomposition. Both sides restated against TODAY's ``voided``; ``keep`` must match the diff's."""
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
    if not delta:
        return
    (ba, bn), (aa, an) = delta["before"], delta["after"]
    print(f"\n  agree {ba}/{bn} -> {aa}/{an}  ({delta['moved']} picks moved, "
          f"{delta['reruled']} rulings moved, {delta['voided']} voided)")


# ── the filesystem-facing functions ────────────────────────────────────────────────
# Everything above is pure. Both gates share ONE corpus walk, so neither can see a different corpus.

#: Observation keys a fixture may carry beyond its Correction's snapshot (ADR-0050's reseeding
#: payload). They change HOW a fixture replays, never WHAT the human ruled.
SEEDED_OBS_KEYS = ("own_prizes", "search_begin_input")


def write_json_artifact(path, doc) -> None:
    """Write a gate artifact as **LF-framed UTF-8 bytes**: `Path.write_text` on Windows rewrites every
    newline, turning a 40-row data change into a whole-file rewrite of a committed LF baseline."""
    from pathlib import Path
    import json as _json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json.dumps(doc, indent=2).encode("utf-8"))


class RecaptureRefused(RuntimeError):
    """A `capture` that would overwrite a verdict still owed a ruling (ADR-0094). Carries EVERY offending key."""

    def __init__(self, keys):
        self.keys = list(keys)
        # ASCII only: this reaches the operator on stderr, which neither lab reconfigures to UTF-8,
        # so an em dash arrives as a replacement char on a Windows console.
        super().__init__(
            "re-capture refused: {} frame(s) would move in the FAIL direction with no ruling on "
            "record -- {}. A baseline is a RULING RECORD (CLAUDE.md): rule the flip first (a wave "
            "packet), or use `restamp` if you only need the recorded revision moved."
            .format(len(self.keys), ", ".join(self.keys)))


def decision_fail_keys(diff: dict) -> list:
    """The Decision Gate's ``REGRESSION`` keys, READ off a `decider_lab_diff` rather than re-classified."""
    return sorted(r["key"] for r in (diff or {}).get("rows") or [] if r.get("verdict") == "REGRESSION")


def discrimination_fail_keys(diff: dict) -> list:
    """The Discrimination Gate's ``OK -> MISS`` keys, read off a `leaf_lab_diff` — a named reader, so
    the two labs are ACTUALLY symmetric rather than merely described as such."""
    return sorted(f["key"] for f in (diff or {}).get("ok_to_miss") or [])


def guarded_capture(out, fresh, *, index, diff_fn, fail_keys_fn, write) -> int:
    """The ruling-gated write shared by both labs: diff the outgoing baseline, refuse on an unruled
    fail-direction move, else ``write()``. WHERE to capture from is `CAPTURE_POINT`, not this guard."""
    from pathlib import Path
    import json as _json
    out = Path(out)
    if out.exists():
        outgoing = _json.loads(out.read_text(encoding="utf-8"))
        try:
            refuse_unruled_recapture(fail_keys_fn(diff_fn(outgoing, fresh)), index=index)
        except RecaptureRefused as refused:   # an operator error, not a crash: say so plainly and
            print(f"REFUSED: {refused}")      # leave the committed baseline untouched
            return 1
    write()
    return 0


def unruled_recapture_moves(fail_keys, *, index) -> list:
    """The fail-direction frames carrying NO ruling. One predicate, ``index.get(key)``: no special cases."""
    return sorted(k for k in (fail_keys or ()) if not (index or {}).get(k))


def refuse_unruled_recapture(fail_keys, *, index) -> None:
    """Raise `RecaptureRefused` if any fail-direction frame carries no ruling; silent otherwise (ADR-0094)."""
    offenders = unruled_recapture_moves(fail_keys, index=index)
    if offenders:
        raise RecaptureRefused(offenders)


def restamp_artifact(path, git_rev: str) -> dict:
    """Rewrite ONLY a committed artifact's recorded ``git_rev``; never re-reads the build (ADR-0094).
    Refuses a document carrying none — adding the field would let a re-stamp manufacture provenance."""
    from pathlib import Path
    import json as _json
    path = Path(path)
    doc = _json.loads(path.read_text(encoding="utf-8"))
    if "git_rev" not in doc:
        # ASCII, for the reason `RecaptureRefused` states: this reaches an operator on a console the
        # labs do not reconfigure, and dev is Windows (CLAUDE.md).
        raise ValueError(f"{path} carries no `git_rev` -- not a gate baseline, refusing to add one")
    doc["git_rev"] = str(git_rev)
    write_json_artifact(path, doc)
    return doc


def correction_frame_key(correction) -> str:
    """One Correction's **Frame Key**, and the ONLY way any instrument derives one (ADR-0087 decision 2)."""
    from train.blunder.correction import identity_key
    return frame_key_of(*identity_key(correction))


def keyed_corrections(store=None, *, predicate=None) -> list:
    """**THE Corpus Reader** — ``[(frame_key, Correction), ...]``, records CONSTRUCTED via
    ``load_corrections`` and keys DERIVED (ADR-0087). Pairs, not a dict: a dict collapses conflicts."""
    from train.blunder.store import DEFAULT_ROOT, load_corrections

    corrections = load_corrections(store if store is not None else DEFAULT_ROOT)
    return [(correction_frame_key(c), c)
            for c in corrections if predicate is None or predicate(c)]


def iter_keyed_fixtures(fixtures_dir=None):
    """``(path, fixture, frame_key, Claims)`` per fixture declaring a ``frame_key`` — THE one corpus walk."""
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
    """Does this claim DECLARE that it departs from its Correction? Exactly two escapes (ADR-0082): an
    ``owner``, or a ``why`` whose ``ruled`` date matches `RULED_RE`. A malformed date is rejected, never raised on."""
    if held_out_owner(claim):
        return True
    ruled, why = getattr(claim, "ruled", None), getattr(claim, "why", None)
    return bool(why) and isinstance(ruled, str) and RULED_RE.match(ruled) is not None


def claim_agreement(fixtures_dir=None, store=None) -> list[dict]:
    """Every committed fixture whose Decision Claim departs from its **Correction** without declaring it.
    Findings: ``no_record`` / ``obs_mismatch`` (reported regardless of the escapes) / ``disagreement``."""
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
    """Top-level observation keys on which two boards differ, ignoring `SEEDED_OBS_KEYS`."""
    if fixture_obs is None or record_obs is None:
        return []
    keys = (set(fixture_obs) | set(record_obs)) - set(SEEDED_OBS_KEYS)
    return sorted(k for k in keys if fixture_obs.get(k) != record_obs.get(k))


def held_out_frames(fixtures_dir=None) -> dict:
    """The **Held-out Ledger**, ``{frame key: owner}``: the DECISION claim's owner holds a whole frame out."""
    out = {}
    for _path, _fx, key, claims in iter_keyed_fixtures(fixtures_dir):
        owner = held_out_owner(claims.decision) if claims.decision else None
        if owner:
            out[key] = owner
    return out


def ruling_index(store=None, *, reviewed_path=None, fixtures_dir=None) -> dict:
    """**THE Ruling Index** — ``{frame key: (Ruling, ...)}`` over every store a ruling can live in
    (ADR-0088). Read-only; the join is DERIVED inside the one corpus walk. Stores are injectable."""
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
    """`reviewed.json` entries matching NO committed Correction — they rule on nothing, and silently."""
    from train.blunder.reviewed import load_reviewed, review_key

    reviewed = load_reviewed(reviewed_path) if reviewed_path is not None else load_reviewed()
    reachable = {review_key(c) for _key, c in keyed_corrections(store)}
    return [(k, entry) for k, entry in sorted(reviewed.items()) if k not in reachable]


def equivalence_index(store=None) -> dict:
    """``{Frame Key: {option index: class}}`` over the committed corpus (ADR-0091), on the SAME corpus
    walk the rulings use. A property of the CORPUS, never of a capture. Trivial frames are omitted."""
    from common.option_equivalence import option_equivalence

    out = {}
    for key, correction in keyed_corrections(store):
        obs = correction.obs or {}
        eq = option_equivalence((obs.get("select") or {}).get("option") or [], obs)
        if eq:
            out[key] = eq
    return out


def classes_of(equiv) -> list:
    from common.option_equivalence import classes
    return classes(equiv)


def picks_as_set(pick):
    """A pick compared as a SET: a multi-pick's index ORDER is not a decision, so a reorder is not a move."""
    return None if pick is None else frozenset(pick)


def satisfies_human(chosen, correct, *, equiv=None) -> bool:
    """Does ``chosen`` satisfy the ruling: ``correct`` is a CONSTRAINT, so ``correct ⊆ chosen`` (ADR-0085
    Amendment J). ``correct == []`` is a DECLINE, checked FIRST — ⊆ would make every frame agree."""
    if chosen is None or correct is None:
        return False
    if not correct:                       # a recorded DECLINE — exact, never subset
        return not chosen
    if not equiv:
        return picks_as_set(correct) <= picks_as_set(chosen)
    from collections import Counter

    from common.option_equivalence import class_of

    # COUNTING, not membership: a class widens WHICH option satisfies a ruled card, never lets one
    # pick satisfy two. Classes PARTITION the menu, so this is an exact bipartite matching.
    picked = picks_as_set(chosen)
    want = Counter(frozenset(class_of(equiv, c)) for c in picks_as_set(correct))
    return all(len(cls & picked) >= n for cls, n in want.items())


def records_a_decline_it_cannot_state(correction, obs) -> bool:
    """Does this Correction sit on an OPTIONAL select (``minCount == 0``) at **decision** scope while
    asserting only the agent's own pick? REPORTS, never excludes (Issue #251). Reads defensively."""
    if getattr(correction, "scope", None) != "decision":
        return False
    select = ((obs or {}).get("select") or {})
    if int(select.get("minCount") or 0) != 0:
        return False
    chosen = getattr(correction, "chosen", None) or []
    correct = getattr(correction, "correct", None) or []
    return sorted(chosen) == sorted(correct)


#: `build_correction`'s rules as ``{slug: the sentence a readout prints}`` — ONE source, so the
#: predicate and the printer cannot describe a rule differently. The slugs are what tests assert on.
REFUSED_SHAPE_RULES = {
    "unknown_source": "`source` is not one of the two recorded sources",
    "unknown_scope": "`scope` is not one of decision / turn",
    "correct_off_the_menu": "`correct` does not index the Anchor's own options",
    "turn_correct_equals_chosen": "a turn-scope `correct` equal to `chosen` asserts nothing — it "
                                  "must name the first DIVERGENT option at the Anchor",
    "unprovable_decline": "an empty `correct` at decision scope is a DECLINE, recordable only where "
                          "the record's `obs` PROVES the select optional (minCount 0)",
}


def shape_the_constructor_would_refuse(correction) -> list:
    """Which `REFUSED_SHAPE_RULES` an ALREADY-COMMITTED record breaks; empty = the writer would have
    accepted it. Every applicable rule is reported. `is_valid_category` is deliberately not re-applied."""
    from train.blunder.correction import SCOPES, SOURCES, select_min_count

    broken = []
    if getattr(correction, "source", None) not in SOURCES:
        broken.append("unknown_source")
    scope = getattr(correction, "scope", None)
    if scope not in SCOPES:
        return broken + ["unknown_scope"]

    correct = getattr(correction, "correct", None) or []
    chosen = getattr(correction, "chosen", None) or []
    n_options = len(((getattr(correction, "decision", None) or {}).get("options")) or [])
    if not correct:
        if scope == "decision" and select_min_count(getattr(correction, "obs", None)) != 0:
            broken.append("unprovable_decline")
    else:
        # The constructor's own test, verbatim — including that `bool` is an `int`, so it would admit
        # `correct: [True]` as index 1. The audit asks what the writer WOULD refuse, not what it should.
        if any(not isinstance(i, int) or i < 0 or i >= n_options for i in correct):
            broken.append("correct_off_the_menu")
        if scope == "turn" and set(correct) == set(chosen):
            broken.append("turn_correct_equals_chosen")
    return broken


def refused_shapes(store=None) -> list:
    """Every committed Correction carrying a **Refused Shape**. Corpus-wide; it reaches no verdict."""
    out = []
    for key, c in keyed_corrections(store):
        violations = shape_the_constructor_would_refuse(c)
        if violations:
            out.append({"key": key, "id": getattr(c, "id", None),
                        "scope": getattr(c, "scope", None), "violations": violations})
    return out


def off_policy_frames(store=None) -> dict:
    """``{frame key: reason}`` per Correction ruled **OFF-POLICY** (Issue #412). It reaches no verdict."""
    from train.blunder.off_policy import OFF_POLICY, RULINGS, ruling_key
    out = {}
    for key, c in keyed_corrections(store):
        ruling = RULINGS.get(ruling_key(c))
        if ruling is not None and ruling.verdict == OFF_POLICY:
            out[key] = ruling.reason
    return out


def print_off_policy_readout(off_policy: dict, *, present=(), moved=()) -> None:
    """Names the OFF-POLICY frames graded here, loudly for those that MOVED. Silent at zero."""
    hits = sorted(set(present) & set(off_policy))
    if not hits:
        return
    print(f"\n  OFF-POLICY ({len(hits)}) — graded anyway, NEVER excluded (Issue #412): the play that "
          f"opened these follow-up selects was itself ruled wrong. Reasons: "
          f"tools/train/blunder/off_policy.py")
    flagged = sorted(set(moved) & set(hits))
    if flagged:
        print(f"    ⚠️ {len(flagged)} of them MOVED in the fail direction — this verdict rests on a "
              f"board the agent should never have reached:")
        for key in flagged:
            reason = " ".join((off_policy.get(key) or "").split())
            print(f"      {key:<26} {reason[:88]}{'…' if len(reason) > 88 else ''}")


def rows_by_key(rpt: dict, *, keep=None) -> dict:
    """A capture's rows by **Frame Key**. ``keep`` is passed in, so a diff and its `ruling_moves` share one population."""
    return {r["key"]: r for r in (rpt.get("rows") or [])
            if r.get("key") and (keep is None or keep(r))}


def _scorable(row) -> bool:
    return not row.get("unscorable")


def ruling_moves(before: dict, after: dict, *, keep=None) -> list:
    """Frames present in BOTH captures whose Correction's ``correct`` changed (**Ruling Move**, ADR-0087).
    Emitted independently of whether the agent's pick moved, and that independence IS the fix."""
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
    if not moves:
        return
    print(f"\n  ⚠️ RULING MOVED ({len(moves)}) — the human re-ruled these frames; reported, never gating:")
    for m in moves:
        print(f"    {m['key']}  correct {m['before']} -> {m['after']}")


#: The one actionable sentence a **Stale Baseline** frame is owed, and the ONE copy any code reads.
#: Restated in prose in `docs/ci.md` and `leaf-gate-main.yml`; if the rule changes, all of them move.
CAPTURE_POINT = ("re-capture at a commit carrying the ruling but NOT the change under test, "
                 "then re-run")


def print_stale_baseline(entries) -> None:
    """The ``ok_to_miss`` flips whose ruling ALSO moved. Excuses nothing: it fixes the SENTENCE, not the redness."""
    if not entries:
        return
    print(f"\n  ⚠️ STALE BASELINE ({len(entries)}) — the baseline predates a re-ruling on these "
          f"frames. Their OK -> MISS below is the REFERENCE moving, not the build; they still gate:")
    for f in entries:
        b, a = f.get("before") or {}, f.get("after") or {}
        print(f"    {f['key']}  correct {b.get('correct')} -> {a.get('correct')}"
              f"   rank {b.get('correct_rank')} -> {a.get('correct_rank')}")
    print(f"    -> {CAPTURE_POINT}.")


def decider_lab_diff(before: dict, after: dict, *, voided=(), equiv=None) -> dict:
    """Per-frame DECISION movement between two Decider Lab captures, classified by ``satisfies_human``
    (never equality): REGRESSION / FIX / NEUTRAL / UNLABELLED. ``voided`` is reported, not excluded."""
    norm = picks_as_set

    b, a = rows_by_key(before), rows_by_key(after)
    rows = []
    for k in sorted(b.keys() & a.keys()):
        was, now = b[k].get("chosen"), a[k].get("chosen")
        if norm(was) == norm(now):
            continue
        correct = a[k].get("correct")
        # Resolved from TODAY's corpus, never from either capture: restating both sides against one
        # map is what keeps a diff from grading its two halves under two different oracles.
        eq = (equiv or {}).get(k)
        if correct is None:
            verdict = "UNLABELLED"
        elif (satisfies_human(now, correct, equiv=eq)
              and not satisfies_human(was, correct, equiv=eq)):
            verdict = "FIX"
        elif (satisfies_human(was, correct, equiv=eq)
              and not satisfies_human(now, correct, equiv=eq)):
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
                # The SAME predicate the verdicts key on, so gate and readout cannot form two ideas
                # of "matches the human". None = the row carries no gradeable ruling.
                agrees=lambda r: (None if r.get("correct") is None or r.get("chosen") is None
                                  else satisfies_human(r["chosen"], r["correct"],
                                                       equiv=(equiv or {}).get(r["key"]))),
                moved=lambda x, y: norm(x.get("chosen")) != norm(y.get("chosen")))}
