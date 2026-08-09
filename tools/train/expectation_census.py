"""**The expectation-node census** (Issue #394) — what `common.board_expectation` reaches, what it
refuses, and how wide the enumeration each refused family would produce.

* **`--families`** (default) — refused `_PLAY` steps grouped by `expectation`'s own refusal message.
* **`--sizes`** — the pool a widened enumerator would range over: per LEG, their UNION
  (disjunction), their PRODUCT (conjunction), `C(pool, m)`. What `BRANCH_CAP` is re-checked against.

DLL-free: the trace IS the native side. Minutes over the full corpus; `--limit N` for a subset.

Usage:
    python tools/train/expectation_census.py                    # the family backlog
    python tools/train/expectation_census.py --sizes            # the branching measurement
    python tools/train/expectation_census.py --limit 40 --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

# Self-bootstrapping, like every sibling CLI here: the Usage lines above are bare
# `python tools/train/...`, which cannot run from a clean checkout without this.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from common import apply_option as seam  # noqa: E402
from common import board_choice as bc  # noqa: E402
from common import board_delta, board_expectation as be  # noqa: E402
from common import snapshot_coverage as sc  # noqa: E402
from common.fetch_closure import WINDOW, fetch_target_matches  # noqa: E402
from common.state_model import StateModel  # noqa: E402
from common.state_value import state_value  # noqa: E402
from common.strategy.context import _PLAY  # noqa: E402
from train.apply_parity import TRACES, _card_of, chosen_option, load, offline_combat  # noqa: E402

#: Refusal-message fragments, matched as substrings of the message TAIL (after ``"<id> <name>: "``)
#: and ordered MOST-SPECIFIC-FIRST.
_BUCKETS = (
    "more than one revealing clause", "no `draw`/`fetch` clause", "consults RNG",
    "its `cost` names no target", "`amount`", "this seam cannot decide",
    "DIFFERENT dig depths", "a dig on CONJUNCTION legs",
    "only an Item or a Supporter", "`dest`", "no target it can reach is still unseen",
    "a `draw` is an n-card window", "-zone search carries NO chance", "clause key(s)",
    "it carries a non-revealing clause", "no target it can reach has any availability",
    "select context", "option kind", "no `CardStat`", "reveal names hand index",
    "the model carries no source observation",
)


def bucket_of(message: str) -> str:
    """Falls back to a truncated message, so a NEW refusal gets its own row."""
    tail = message.split(": ", 1)[-1]
    return next((b for b in _BUCKETS if b in tail), tail[:70])


def leg_pool(model, clause: dict) -> dict:
    """A SIZING instrument, not a second predicate: the WINDOW reading prices a `dig`, so only the three
    still-undecidable fields are stripped — a leg blocked by one has a pool, and its size is the report."""
    probe = {k: v for k, v in clause.items() if k not in ("trigger", "condition", "name_family")}
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and fetch_target_matches(probe, model.card_stat(cid), reading=WINDOW)}


def _census_shed(model, option, picks):
    """A STAND-IN for `Pilot.cost_shed_indices`, sound ONLY for "can the node enumerate this step?".
    It pays whenever the hand holds cards, so the enumerated figure is an UPPER BOUND."""
    hand = ((model.source_obs.get("current") or {}).get("players") or [{}])[
        int(getattr(model, "my_index", 0))].get("hand") or ()
    return [i for i in range(len(hand)) if i != option.get("index")][:picks]


def walk(paths, *, combat):
    """BOTH reveal nodes are asked, because a reveal is resolved by whichever owns its zone:
    `board_expectation` for a hidden DECK search, `board_choice` for a face-up DISCARD one."""
    effects = combat.effects
    rows, enumerated, choices, refused = [], Counter(), Counter(), 0
    #: The VISIBLE-zone half, keyed by card: `--sizes` builds rows for REFUSED steps only, so a
    #: discard search vanishes from that report the moment it starts enumerating.
    discard_sizes: dict = defaultdict(list)
    for path in paths:
        body = load(path)
        frames = body.get("frames") or []
        decks = (body.get("meta") or {}).get("decks") or [[], []]
        for k in range(len(frames) - 1):
            option = chosen_option(frames[k])
            if not option or int(option.get("type", -1)) != _PLAY:
                continue
            obs, nxt = frames[k]["obs"], frames[k + 1]["obs"]
            seat = (obs.get("current") or {}).get("yourIndex", 0)
            # The parity lane's incomparable steps: the next frame is the OPPONENT's perspective, so
            # this census and that lane report the same denominator.
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
                enumerated[len(be.expectation(pre, option, seat_index=seat, shed=_census_shed,
                                              score=state_value).classes)] += 1
                continue
            except Exception as exc:
                message = str(exc)
            try:                                  # the sibling node: a visible zone is a CHOICE
                n = len(bc.deferred_target(pre, option, seat_index=seat).classes)
                choices[n] += 1
                me = ((obs.get("current") or {}).get("players") or [{}])[seat] or {}
                discard_sizes[card_id].append((len(me.get("discard") or ()), n))
                continue
            except Exception:
                pass                              # neither node reaches it — it is a real refusal
            rows.append((card_id, bucket_of(message), _facts(pre, combat, card_id, obs, seat)))
    return rows, enumerated, choices, discard_sizes, refused


def _facts(model, combat, card_id, obs, seat) -> dict:
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


def report_families(rows, enumerated, choices, refused, cards, out=print) -> None:
    by_bucket: Counter = Counter()
    per_card: dict = defaultdict(Counter)
    for card_id, bucket, _f in rows:
        by_bucket[bucket] += 1
        per_card[bucket][f"{card_id} {(cards.get(str(card_id)) or {}).get('name')}"] += 1
    chance, choice = sum(enumerated.values()), sum(choices.values())
    total = chance + choice
    share = f" ({100.0 * total / refused:.1f}%)" if refused else ""
    both = Counter(enumerated) + Counter(choices)
    out(f"\n_PLAY steps the deterministic seam refuses: {refused}")
    out(f"  ENUMERATED by a reveal node: {total}{share}")
    out(f"    board_expectation (chance node, hidden zone): {chance}")
    out(f"    board_choice      (choice node, visible zone): {choice}")
    out(f"  class-count distribution: {dict(sorted(both.items()))}")
    out(f"  truncated at BRANCH_CAP={be.BRANCH_CAP}: "
        f"{sum(n for c, n in both.items() if c >= be.BRANCH_CAP)}")
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


def report_discard_sizes(discard_sizes, cards, out=print) -> None:
    """The discard's SIZE (what the search looks at) beside the CLASS count (what it resolved to);
    the gap between them is the duplicate-collapse doing its job."""
    if not discard_sizes:
        return
    out("")
    out(f"{'card':>5} {'name':22} {'n':>4} {'discard size':>16} {'classes':>16}")
    out("-" * 68)
    for card_id, pairs in sorted(discard_sizes.items(), key=lambda kv: -len(kv[1])):
        name = ((cards.get(str(card_id)) or {}).get("name") or "?")[:22]
        out(f"{card_id:>5} {name:22} {len(pairs):>4} "
            f"{_span(p for p, _c in pairs):>16} {_span(c for _p, c in pairs):>16}")
    out("")
    out("A class count BELOW the discard size is the duplicate collapse: copies of one card in the")
    out("pile are ONE decision, because `option_fingerprint` strips `serial`.")


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
    rows, enumerated, choices, discard_sizes, refused = walk(paths, combat=combat)
    cards = json.loads((Path(__file__).resolve().parents[2] / "tools" / "meta_tracker"
                        / "cards.json").read_text(encoding="utf-8"))

    if args.families or not args.sizes:
        report_families(rows, enumerated, choices, refused, cards)
        report_discard_sizes(discard_sizes, cards)
    if args.sizes:
        report_sizes(rows, cards)
    if args.json:
        args.json.write_bytes(json.dumps(
            {"refused": refused, "class_counts": dict(enumerated),
             "choice_class_counts": dict(choices),
             "rows": [{"card": c, "bucket": b, **{k: list(v) if isinstance(v, tuple) else v
                                                  for k, v in f.items()}} for c, b, f in rows]},
            indent=1).encode("utf-8"))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
