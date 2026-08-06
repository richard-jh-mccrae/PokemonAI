"""**The expectation-node census** (Issue #394) — what `common.board_expectation` reaches, what it
refuses, and how wide the enumeration each refused family would produce actually is.

`tools/train/apply_parity.py` answers *"does the closed-form transition agree with the engine?"* over
the committed native traces. This answers the sibling question the vocabulary work needs: *"of the
`_PLAY` steps the deterministic seam refuses, which does the expectation node enumerate, why does it
refuse the rest, and what would a widening COST in branching?"*

Two reports, one walk:

* **`--families`** (default) — every refused `_PLAY` step grouped by `expectation`'s own refusal
  message, with the per-card breakdown. Reproduces the counted backlog in `board_expectation`'s
  header, which is what makes it a positive control rather than a fresh claim: if the buckets stop
  summing to that table, this instrument is broken and not the codebase.
* **`--sizes`** — for every refused step carrying a reveal clause, the pool the widened enumerator
  would range over: per LEG, their UNION (the disjunction reading), their PRODUCT (the conjunction
  reading), and `C(pool, m)` for a multi-card delivery. This is the measurement `BRANCH_CAP` is
  re-checked against, per Issue #394's acceptance criterion — *"the measurement is the acceptance
  evidence, not a claim."*

DLL-free by construction, exactly like the parity lane it borrows its walk from: the trace IS the
native side and cgpy's committed tables supply the card facts, so this runs on Windows and Linux
alike. Minutes over the full 377-trace corpus; `--limit N` for a subset.

Usage:
    python tools/train/expectation_census.py                    # the family backlog
    python tools/train/expectation_census.py --sizes            # the branching measurement
    python tools/train/expectation_census.py --limit 40 --json out.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

from common import apply_option as seam
from common import board_delta, board_expectation as be
from common import snapshot_coverage as sc
from common.fetch_closure import fetch_target_matches
from common.state_model import StateModel
from common.strategy.context import _PLAY
from train.apply_parity import TRACES, _card_of, _chosen_option, _load, offline_combat

#: The refusal-message fragments `expectation` raises, each mapped to the backlog bucket it names.
#: Matched as substrings of the message TAIL (the part after ``"<id> <name>: "``), because the
#: message is destined for the telemetry line and is grouped by exactly that string
#: (`apply_option.EngineResolved.clause_gap`). Ordered most-specific-first for the same reason
#: `_check_clause`'s own gates are.
_BUCKETS = (
    "more than one revealing clause", "no `draw`/`fetch` clause", "consults RNG",
    "its `cost` names no target", "`amount`", "not the unconditional",
    "only an Item or a Supporter", "`dest`", "no target it can reach is still unseen",
    "a `draw` is an n-card window", "-zone search carries NO chance", "clause key(s)",
    "it carries a non-revealing clause", "no target it can reach has any availability",
    "select context", "option kind", "no `CardStat`", "reveal names hand index",
    "the model carries no source observation",
)


def bucket_of(message: str) -> str:
    """The backlog bucket a refusal belongs to. Falls back to a truncated message, so a NEW refusal
    shows up as its own row rather than being folded into a neighbour — the same fail-loud rule the
    seam keeps for an unrecognised clause key."""
    tail = message.split(": ", 1)[-1]
    return next((b for b in _BUCKETS if b in tail), tail[:70])


def leg_pool(model, clause: dict) -> dict:
    """`board_expectation.outcome_pool` for ONE leg, with the four reach fields stripped.

    Stripping them is deliberate and is what makes this a SIZING instrument rather than a second
    reach predicate: a leg blocked by a `dig` or a `name_family` still has a pool, and its size is
    the number this census exists to report. It endorses nothing — `fetch_is_unconditional` remains
    the only answer to *"is this a search we may act on?"* (ADR-0087)."""
    probe = {k: v for k, v in clause.items()
             if k not in ("dig", "trigger", "condition", "name_family")}
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and fetch_target_matches(probe, model.card_stat(cid))}


def walk(paths, *, combat):
    """Every refused `_PLAY` step, as ``(card_id, bucket, facts)`` rows. One pass serves both
    reports — the walk is the expensive half (a `StateModel` per step), and running it twice to
    print two tables would double a minutes-long measurement for nothing."""
    effects = combat.effects
    rows, enumerated, refused = [], Counter(), 0
    for path in paths:
        body = _load(path)
        frames = body.get("frames") or []
        decks = (body.get("meta") or {}).get("decks") or [[], []]
        for k in range(len(frames) - 1):
            option = _chosen_option(frames[k])
            if not option or int(option.get("type", -1)) != _PLAY:
                continue
            obs, nxt = frames[k]["obs"], frames[k + 1]["obs"]
            seat = (obs.get("current") or {}).get("yourIndex", 0)
            # The parity lane's incomparable steps: the next frame is the OPPONENT's perspective, so
            # there is nothing on my side to compare. Skipped here for the same reason, so this
            # census and that lane report the same denominator (706, not 712).
            if (nxt.get("current") or {}).get("yourIndex") != seat:
                continue
            card_id = _card_of(obs, option, seat)
            deck = decks[seat] if seat < len(decks) else []
            pre = StateModel.build(obs, combat=combat, my_index=seat, deck=deck)
            cover = effects.clauses_cover(card_id) if card_id else None
            if not seam.must_expand(seam.apply_option(pre, option, clauses_cover=cover)):
                continue                        # the deterministic seam handled it
            refused += 1
            try:
                enumerated[len(be.expectation(pre, option, seat_index=seat).classes)] += 1
                continue
            except Exception as exc:
                message = str(exc)
            rows.append((card_id, bucket_of(message), _facts(pre, combat, card_id, obs, seat)))
    return rows, enumerated, refused


def _facts(model, combat, card_id, obs, seat) -> dict:
    """The clause + board facts both reports read, gathered once per refused step."""
    every = tuple(board_delta.card_clauses(combat, card_id))
    rev = [c for c in every if c.get("kind") in sc.REVEALING_CLAUSES]
    me = ((obs.get("current") or {}).get("players") or [{}])[seat] or {}
    pools = [leg_pool(model, c) for c in rev]
    union: dict = {}
    for p in pools:
        union.update(p)
    product = 1
    for p in pools:
        product *= len(p)
    amount = rev[0].get("amount") if rev else None
    return {
        "legs": tuple(len(p) for p in pools),
        "union": len(union),
        "product": product if pools else 0,
        "amount": amount,
        "choice": bool(rev) and all(c.get("choice") for c in rev),
        "hand": len(me.get("hand") or ()),
        "bench_free": int(me.get("benchMax") or 5) - len(me.get("bench") or ()),
    }


def report_families(rows, enumerated, refused, cards, out=print) -> None:
    by_bucket: Counter = Counter()
    per_card: dict = defaultdict(Counter)
    for card_id, bucket, _f in rows:
        by_bucket[bucket] += 1
        per_card[bucket][f"{card_id} {(cards.get(str(card_id)) or {}).get('name')}"] += 1
    total = sum(enumerated.values())
    share = f" ({100.0 * total / refused:.1f}%)" if refused else ""
    out(f"\n_PLAY steps the deterministic seam refuses: {refused}")
    out(f"  enumerated by board_expectation: {total}{share}")
    out(f"  class-count distribution: {dict(sorted(enumerated.items()))}")
    out(f"  truncated at BRANCH_CAP={be.BRANCH_CAP}: "
        f"{sum(n for c, n in enumerated.items() if c >= be.BRANCH_CAP)}")
    out(f"\nrefusal buckets ({len(rows)} steps):")
    for bucket, n in by_bucket.most_common():
        out(f"  {n:5d}  {bucket}")
        for card, c in per_card[bucket].most_common(6):
            out(f"           {c:4d}  {card}")


def report_sizes(rows, cards, out=print) -> None:
    per_card: dict = defaultdict(list)
    for card_id, _bucket, facts in rows:
        if facts["legs"]:
            per_card[card_id].append(facts)
    out(f"\n{'card':>5} {'name':22} {'n':>4} {'legs':>12} {'union':>14} {'product':>14} "
        f"{'C(pool,m)':>14}")
    out("-" * 96)
    for card_id, fs in sorted(per_card.items(), key=lambda kv: -len(kv[1])):
        name = ((cards.get(str(card_id)) or {}).get("name") or "?")[:22]
        m = fs[0]["amount"] if isinstance(fs[0]["amount"], int) else None
        csub = (_span(comb(f["union"], min(m, f["union"])) for f in fs)
                if m and m > 1 else "-")
        out(f"{card_id:>5} {name:22} {len(fs):>4} "
            f"{str(Counter(f['legs'] for f in fs).most_common(1)[0][0]):>12} "
            f"{_span(f['union'] for f in fs):>14} {_span(f['product'] for f in fs):>14} "
            f"{csub:>14}")
    out("\nlegs = the most common per-leg pool tuple; union/product/C(pool,m) = min-max (median).")
    out("A `product` above BRANCH_CAP means a conjunction would TRUNCATE on that board; a union "
        "never branches wider than its own pool.")


def _span(values) -> str:
    vs = sorted(values)
    return f"{vs[0]}-{vs[-1]} ({vs[len(vs) // 2]})" if vs else "-"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="replay only the first N traces")
    ap.add_argument("--sizes", action="store_true", help="the branching measurement")
    ap.add_argument("--families", action="store_true", help="the refusal backlog (default)")
    ap.add_argument("--json", type=Path, default=None, help="also write the rows as JSON")
    args = ap.parse_args(argv)

    paths = sorted(TRACES.glob("*.trace.json.gz"))[:args.limit or None]
    print(f"traces: {len(paths)}")
    combat = offline_combat()
    rows, enumerated, refused = walk(paths, combat=combat)
    cards = json.loads((Path(__file__).resolve().parents[2] / "tools" / "meta_tracker"
                        / "cards.json").read_text(encoding="utf-8"))

    if args.families or not args.sizes:
        report_families(rows, enumerated, refused, cards)
    if args.sizes:
        report_sizes(rows, cards)
    if args.json:
        args.json.write_bytes(json.dumps(
            {"refused": refused, "class_counts": dict(enumerated),
             "rows": [{"card": c, "bucket": b, **{k: list(v) if isinstance(v, tuple) else v
                                                  for k, v in f.items()}} for c, b, f in rows]},
            indent=1).encode("utf-8"))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
