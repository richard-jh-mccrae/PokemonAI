"""Build the shipped card-function-tag table (see docs/card-functions.md).

Probes every Trainer in the engine to derive behavioral tags, merges static + curated-override
tags, and writes ``{cardId: [tags]}`` to ``common/card_functions.json``. Lib-using — run offline.

Re-runs ACCUMULATE by default: a tag once observed is never lost, so successive stochastic runs
only improve coverage of the rng-gated tags. ``--fresh`` rebuilds from scratch.

Usage:
    python tools/build_card_functions.py [--out PATH] [--limit N] [--overrides PATH] [--fresh]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))                          # meta_tracker
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # cg (lazy)

from common.card_tags import is_card_key                   # noqa: E402  the ONE reserved-key rule
from meta_tracker.card_functions import accumulate_tables, build_function_table  # noqa: E402
from meta_tracker.cards import load_cards                     # noqa: E402
from meta_tracker.probe_cards import (  # noqa: E402
    _ability_pokemon, probe_card, probe_evolution, probe_pokemon, probe_pokemon_ability)

DEFAULT_OUT = (Path(__file__).resolve().parents[1]
               / "src" / "common" / "card_functions.json")
DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "meta_tracker" / "function_overrides.json"
_TRAINER_CATS = {"item", "supporter", "stadium", "tool"}
_COMBAT_PASSES = 4   # heal/damage align only ~1-in-N combat games -> probe several & union
_KO_PASSES = 3       # attrition (recycle/energy_denial) aligns ~1-in-N too -> probe several & union


def _merge(recs: list[dict]) -> dict:
    """Union probe records (same actor): concatenate logs and contexts."""
    logs: list = []
    contexts: list = []
    for r in recs:
        logs += r.get("logs", [])
        contexts += r.get("contexts", [])
    return {"actor": recs[0].get("actor"), "logs": logs, "contexts": contexts}


def _merge_into(probes: dict[int, dict], more: dict[int, dict]) -> None:
    """Union ``more`` into ``probes`` per cardId (a mon can have *both* an attack and an Ability)."""
    for cid, rec in more.items():
        probes[cid] = _merge([probes[cid], rec]) if cid in probes else rec


def probe_trainers(cards: dict, *, limit: int | None = None, log=print) -> dict[int, dict]:
    """Probe each Trainer under stable, controlled-combat and attrition scenarios; union them. Combat
    captures heal, attrition captures recycle/energy_denial — the latter two align in only ~1-in-N."""
    ids = [c for c in sorted(cards) if cards[c].get("category") in _TRAINER_CATS]
    if limit:
        ids = ids[:limit]
    probes: dict[int, dict] = {}
    for i, cid in enumerate(ids):
        attempts = [probe_card(cid, cards, attack=False)]                              # stable pass
        attempts += [probe_card(cid, cards, attack=True) for _ in range(_COMBAT_PASSES)]  # combat, variance
        attempts += [probe_card(cid, cards, ko=True) for _ in range(_KO_PASSES)]          # attrition, variance
        recs = [r for r in attempts if r is not None]
        if recs:
            probes[cid] = _merge(recs)
        if log and (i + 1) % 25 == 0:
            log(f"  probed {i + 1}/{len(ids)} trainers ({len(probes)} reached)")
    return probes


def probe_pokemon_pool(cards: dict, *, limit: int | None = None, log=print) -> dict[int, dict]:
    """Probe each Basic Pokémon's attack → ``{cardId: record}`` (Special Conditions / spread / damage)."""
    ids = [c for c in sorted(cards) if cards[c].get("category") == "pokemon"
           and cards[c].get("stage") == "basic"]
    if limit:
        ids = ids[:limit]
    probes: dict[int, dict] = {}
    for i, cid in enumerate(ids):
        rec = probe_pokemon(cid, cards)
        if rec is not None:
            probes[cid] = rec
        if log and (i + 1) % 50 == 0:
            log(f"  probed {i + 1}/{len(ids)} basic Pokémon ({len(probes)} reached)")
    return probes


def probe_pokemon_ability_pool(cards: dict, *, limit: int | None = None, log=print) -> dict[int, dict]:
    """Probe each basic Pokémon that has an Ability → ``{cardId: record}`` (draw/search/accel/dig)."""
    ability_ids = _ability_pokemon()
    ids = [c for c in sorted(cards) if cards[c].get("category") == "pokemon"
           and cards[c].get("stage") == "basic" and c in ability_ids]
    if limit:
        ids = ids[:limit]
    probes: dict[int, dict] = {}
    for i, cid in enumerate(ids):
        rec = probe_pokemon_ability(cid, cards)
        if rec is not None:
            probes[cid] = rec
        if log and (i + 1) % 25 == 0:
            log(f"  probed {i + 1}/{len(ids)} ability mons ({len(probes)} reached)")
    return probes


def probe_evolution_pool(cards: dict, *, limit: int | None = None, log=print) -> dict[int, dict]:
    """Probe each Stage 1/2 Pokémon (evolve up its line) → ``{cardId: record}``, capturing its Ability
    and its COSTLIEST attack."""
    ids = [c for c in sorted(cards) if cards[c].get("category") == "pokemon"
           and cards[c].get("stage") in ("stage1", "stage2")]
    if limit:
        ids = ids[:limit]
    probes: dict[int, dict] = {}
    for i, cid in enumerate(ids):
        rec = probe_evolution(cid, cards)
        if rec is not None:
            probes[cid] = rec
        if log and (i + 1) % 50 == 0:
            log(f"  probed {i + 1}/{len(ids)} evolutions ({len(probes)} reached)")
    return probes


def _load_overrides(path) -> dict[int, list[str]]:
    p = Path(path)
    if p.exists():  # numeric keys only — a leading-underscore "_note" key can document the file
        return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                if is_card_key(k)}
    return {}


def _load_table(path) -> dict[int, list[str]]:
    """The previously-shipped ``{cardId: tags}`` table, to accumulate into (empty if none). Reserved
    keys are SKIPPED rather than `int()`-ed, via `card_tags.is_card_key` (Issue #395 D6.5)."""
    p = Path(path)
    if p.exists():
        return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                if is_card_key(k)}
    return {}


def shipped_bytes(table: dict[int, list[str]]) -> bytes:
    """The shipped store's EXACT bytes for ``table`` — the one writer (Issue #395 D6.4). Binary write
    (`write_text` CRLFs on Windows), `indent=0`, int-sorted: `build_card_effects.py`'s format."""
    payload = {str(cid): tags for cid, tags in sorted(table.items())}
    return json.dumps(payload, ensure_ascii=False, indent=0).encode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    ap.add_argument("--limit", type=int, default=None, help="probe only the first N trainers")
    ap.add_argument("--fresh", action="store_true",
                    help="overwrite from scratch instead of accumulating into the existing table "
                         "(use after changing classify_functions rules, to drop stale tags)")
    args = ap.parse_args()

    cards = load_cards()
    overrides = _load_overrides(args.overrides)
    print(f"probing trainers (limit={args.limit}) …")
    probes = probe_trainers(cards, limit=args.limit)
    print(f"probing basic Pokémon attacks (limit={args.limit}) …")
    _merge_into(probes, probe_pokemon_pool(cards, limit=args.limit))
    print(f"probing basic Pokémon abilities (limit={args.limit}) …")
    _merge_into(probes, probe_pokemon_ability_pool(cards, limit=args.limit))
    print(f"probing evolutions (limit={args.limit}) …")
    _merge_into(probes, probe_evolution_pool(cards, limit=args.limit))
    table = build_function_table(cards, probes, overrides)

    out = Path(args.out)
    # Accumulate by default: union this (stochastic) run into existing table so a tag once
    # observed is never lost and successive runs only *improve* coverage. --fresh starts clean.
    prior = {} if args.fresh else _load_table(out)
    before = sum(len(v) for v in prior.values())
    table = accumulate_tables(table, prior)
    after = sum(len(v) for v in table.values())

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(shipped_bytes(table))
    mode = "fresh" if args.fresh else f"accumulated, +{after - before} new tag-instances"
    print(f"wrote {len(table)} tagged cards ({len(probes)} probed; {mode}) -> {out}")
    if not args.fresh:
        print("note: tags only accumulate — rebuild with --fresh after editing classify rules.")


if __name__ == "__main__":
    main()
