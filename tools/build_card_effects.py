"""Build the shipped Effect-Clause table (ADR-0032 item 6; see card_effects.py).

Drives ``probe_cards.probe_card`` over the Trainer pool, feeds each record to
``classify_effect_clauses`` separately, merges by max, unions ``effect_overrides.json`` by kind,
and writes ``{cardId: [clauses]}`` to ``common/card_effects.json``. Lib-using — run offline.

Re-runs ACCUMULATE by default: a clause once measured is never dropped and amounts only grow;
``--fresh`` rebuilds from scratch. Heal ``restriction`` values are engine-OBSERVED, and on a
conflict with an override the OBSERVED value wins, loudly. ``--limit 0`` skips the trainer probe.
Per-card `_covers` verdicts (Issue #300) ride through from the overrides file verbatim.

Usage:
    python tools/build_card_effects.py [--out PATH] [--limit N] [--overrides PATH]
                                       [--observed PATH] [--observe-restrictions] [--fresh]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))                # meta_tracker
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))    # cg (lazy)

from common import snapshot_coverage                                          # noqa: E402
from meta_tracker.card_effects import (                                        # noqa: E402
    accumulate_effects, apply_observed_restrictions, apply_overrides, build_effect_table)
from meta_tracker.cards import load_cards                                     # noqa: E402
from meta_tracker.probe_cards import probe_card                               # noqa: E402

DEFAULT_OUT = (Path(__file__).resolve().parents[1]
               / "src" / "common" / "card_effects.json")
DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "meta_tracker" / "effect_overrides.json"
DEFAULT_OBSERVED = Path(__file__).resolve().parent / "meta_tracker" / "observed_restrictions.json"
_TRAINER_CATS = {"item", "supporter", "stadium", "tool"}
_COMBAT_PASSES = 4   # heal aligns ~1-in-N combat games (same rationale as functions builder)


def probe_trainer_records(cards: dict, *, limit: int | None = None,
                          log=print) -> dict[int, list[dict]]:
    """Probe each Trainer, keeping the per-pass records SEPARATE → ``{cardId: [records]}``. Records are
    not concatenated: a draw count summed across passes or a rider paired across games is fiction."""
    ids = [c for c in sorted(cards) if cards[c].get("category") in _TRAINER_CATS]
    if limit is not None:
        ids = ids[:limit]
    records: dict[int, list[dict]] = {}
    for i, cid in enumerate(ids):
        attempts = [probe_card(cid, cards, attack=False)]                               # stable
        attempts += [probe_card(cid, cards, attack=True) for _ in range(_COMBAT_PASSES)]  # combat
        recs = [r for r in attempts if r is not None]
        if recs:
            records[cid] = recs
        if log and (i + 1) % 25 == 0:
            log(f"  probed {i + 1}/{len(ids)} trainers ({len(records)} reached)")
    return records


def _load_overrides(path) -> dict[int, list[dict]]:
    p = Path(path)
    if p.exists():  # numeric keys only → "_note" key documents the file
        return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                if k.lstrip("-").isdigit()}
    return {}


def _load_covers(path) -> dict:
    """The hand-ruled ``{cardId: {covers, reason}}`` block, verbatim — never measured, never merged. A
    verdict is a statement ABOUT a clause set, so it rides beside the sets rather than inside them."""
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8")).get(snapshot_coverage.COVERS_KEY) or {}
    notes = {k: v for k, v in raw.items() if str(k).startswith("_")}
    return {**notes, **{k: v for k, v in raw.items() if snapshot_coverage.is_card_key(k)}}


def _load_table(path) -> dict[int, list[dict]]:
    """The previously-shipped ``{cardId: [clauses]}`` table, to accumulate into."""
    p = Path(path)
    if p.exists():
        return snapshot_coverage.clause_lists(json.loads(p.read_text(encoding="utf-8")))
    return {}


_OBSERVED_NOTE = ("Engine-OBSERVED heal restrictions (ADR-0032 item 6; "
                  "probe_restrictions.py): which targets the select offered on a "
                  "seeded board (damaged bench Mega + damaged non-Mega Active). "
                  "Regenerate with build_card_effects.py --observe-restrictions; "
                  "re-stamped after effect_overrides.json on every build — on "
                  "conflict the observed value wins (the engine is the authority).")


def _write_observed(path, observed: dict[int, dict]) -> None:
    payload: dict = {"_note": _OBSERVED_NOTE}
    payload.update({str(cid): entry for cid, entry in sorted(observed.items())})
    Path(path).write_bytes(json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    ap.add_argument("--observed", default=str(DEFAULT_OBSERVED))
    ap.add_argument("--limit", type=int, default=None,
                    help="probe only the first N trainers (0 = skip the trainer probe)")
    ap.add_argument("--observe-restrictions", action="store_true",
                    help="re-measure heal restrictions on the seeded observation board "
                         "and persist them (they re-stamp on every run)")
    ap.add_argument("--fresh", action="store_true",
                    help="overwrite from scratch instead of accumulating into the existing "
                         "table (use after changing classify rules; override edits "
                         "re-stamp on every run)")
    args = ap.parse_args()

    cards = load_cards()
    overrides = _load_overrides(args.overrides)
    print(f"probing trainers for effect clauses (limit={args.limit}) ...")
    records = probe_trainer_records(cards, limit=args.limit)
    table = build_effect_table(cards, records, overrides)

    out = Path(args.out)
    prior = {} if args.fresh else _load_table(out)
    before = sum(len(v) for v in prior.values())
    table = accumulate_effects(table, prior)
    table = apply_overrides(table, overrides)   # stale pre-gate clauses -> hand-verified truth

    observed = _load_overrides(args.observed)   # same numeric-key format
    if args.observe_restrictions:
        from meta_tracker.probe_restrictions import observe_restriction_table  # noqa: E402
        print("observing heal restrictions on the seeded board ...")
        measured, obs_errors, skipped = observe_restriction_table(cards, table)
        observed.update(measured)
        _write_observed(args.observed, observed)
        for cid in skipped:
            print(f"  {cid} {cards.get(cid, {}).get('name')}: skipped "
                  "(restriction outside the board's vocabulary — authored value kept)")
        for cid, err in obs_errors.items():
            print(f"  !! {cid} {cards.get(cid, {}).get('name')}: UNOBSERVED ({err}) "
                  "— authored value kept")
    table, conflicts = apply_observed_restrictions(table, observed)  # engine outranks hands
    for cid, pairs in conflicts.items():
        for authored, obs_r in pairs:
            print(f"  !! RESTRICTION CONFLICT card {cid} {cards.get(cid, {}).get('name')}: "
                  f"authored {authored!r} vs OBSERVED {obs_r!r} — observed value kept")
    after = sum(len(v) for v in table.values())

    out.parent.mkdir(parents=True, exist_ok=True)
    # `_covers` first, so the completeness verdicts are the first thing a reader of the shipped
    # artifact meets rather than something buried past 58 clause lists.
    payload: dict = {snapshot_coverage.COVERS_KEY: _load_covers(args.overrides)}
    payload.update({str(cid): cls for cid, cls in sorted(table.items())})
    problems = snapshot_coverage.covers_problems(payload)
    problems += snapshot_coverage.opponent_draw_problems(payload)
    for problem in problems:
        print(f"  !! COVERS: {problem}")
    if problems:
        raise SystemExit("refusing to write invalid effect clauses")
    # Binary write: `Path.write_text` rewrites LF to CRLF on Windows, which would turn every rebuild
    # into a whole-file diff on a committed store (ADR-0116).
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=0).encode("utf-8"))
    kinds: dict[str, int] = {}
    for cls in table.values():
        for c in cls:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    mode = "fresh" if args.fresh else f"accumulated, +{after - before} new clauses"
    print(f"wrote {len(table)} cards with clauses ({len(records)} probed; {mode}; "
          f"by kind: {kinds}) -> {out}")
    if not args.fresh:
        print("note: measured clauses only accumulate — rebuild with --fresh after "
              "editing classify rules (override edits re-stamp on every run).")


if __name__ == "__main__":
    main()
