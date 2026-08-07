"""Coverage ledger + parity rollup (ADR-0050 M4 item 3).

Builds ``data/engine/coverage.json`` — ``{cardId: {name, status, chains, evidence, updated}}`` —
with per-chain status:

- **verified** — EXERCISED by a committed parity trace (every committed trace replays cleanly
  under the CI gate, so exercise there is proof).
- **derived**  — def straight from the structured tables; correct by construction.
- **seeded**   — def from a text rule (``R-…``): runs, but no trace has pinned it yet.
- **unprobed** — hand-authored (override) chain with no committed-trace evidence.
- **deferred** — explicitly unmodeled; exercising it raises UnsupportedCard.

A card's status is its WEAKEST chain — a Pokémon is only as covered as its least-covered attack.

    python tools/parity/report.py [--print]"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.cards import CardDB  # noqa: E402
from cgpy.chain import load_chain_defs  # noqa: E402
from cgpy.schema import CardType, LogType  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "parity"
LEDGER = REPO / "data" / "engine" / "coverage.json"

_ORDER = {"deferred": 0, "unprobed": 1, "seeded": 2, "derived": 3, "verified": 4}
_TYPE_NAME = {int(CardType.POKEMON): "pokemon", int(CardType.ITEM): "item",
              int(CardType.TOOL): "tool", int(CardType.SUPPORTER): "supporter",
              int(CardType.STADIUM): "stadium", int(CardType.BASIC_ENERGY): "basic-energy",
              int(CardType.SPECIAL_ENERGY): "special-energy"}


def _overrides() -> dict:
    path = REPO / "src" / "cgpy" / "defs" / "chain_overrides.json"
    return json.loads(path.read_text(encoding="utf-8"))


def trace_evidence(paths: list[Path]) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Scan committed traces → ``{chainId: {trace names}}`` + frame totals."""
    evidence: dict[str, set[str]] = {}
    frames = {"total": 0}
    for p in paths:
        with gzip.open(p, "rb") as fh:
            body = json.loads(fh.read().decode("utf-8"))
        name = p.name.replace(".trace.json.gz", "")
        decks = body["meta"]["decks"]

        def cid_of(serial: int) -> int | None:
            if 3 <= serial < 3 + len(decks[0]):
                return decks[0][serial - 3]
            if 63 <= serial < 63 + len(decks[1]):
                return decks[1][serial - 63]
            return None

        def mark(chain_id: str) -> None:
            evidence.setdefault(chain_id, set()).add(name)

        for fr in body["frames"]:
            frames["total"] += 1
            obs = fr["obs"]
            for log in obs.get("logs") or []:
                t = log.get("type")
                if t == int(LogType.ATTACK) and log.get("attackId") is not None:
                    mark(f"attack:{log['attackId']}")
                elif t in (int(LogType.PLAY), int(LogType.ATTACH), int(LogType.EVOLVE)) \
                        and log.get("cardId") is not None:
                    mark(str(log["cardId"]))
            sel = obs.get("select") or {}
            eff = sel.get("effect")
            if isinstance(eff, dict):              # card ref: {"id": …, "serial": …}
                cid = eff.get("id") or cid_of(eff.get("serial") or -1)
                if cid:
                    mark(str(cid))
            elif isinstance(eff, int) and eff > 0:
                cid = cid_of(eff)
                if cid is not None:
                    mark(str(cid))
    return evidence, frames


def ops_in(entry: dict) -> set[str]:
    """Every interpreter op a ChainDef entry can execute — programs, spliced asks, and the
    runtime-synthesized wrappers (`xActivateAsk` around onEvolve/onBench, `xOrderTriggers`)."""
    out: set[str] = set()
    for key in ("play", "rider", "pre"):
        for op in entry.get(key) or []:
            out.add(op["op"])
            for sub in op.get("program") or []:
                out.add(sub["op"])
    ab = entry.get("ability") or {}
    for op in ab.get("program") or []:
        out.add(op["op"])
    for hook in ("onEvolve", "onBench"):
        for op in (entry.get(hook) or {}).get("program") or []:
            out.add(op["op"])
        if entry.get(hook):
            out.add("xActivateAsk")
    if (entry.get("stadium") or {}).get("onBench"):
        out.update(("xBenchCounterDamage", "xOrderTriggers"))
    return out


def chain_status(chain_id: str, defs: dict, overrides: dict,
                 evidence: dict[str, set[str]]) -> str:
    if chain_id in evidence and chain_id in defs and "deferred" not in defs[chain_id]:
        return "verified"
    d = defs.get(chain_id)
    if d is None or "deferred" in d:
        return "deferred"
    if chain_id in overrides:
        return "unprobed"
    seed = d.get("_seed") or {}
    if seed.get("source") in ("vanilla", "plain-pokemon", "basic-energy"):
        return "derived"
    return "seeded"


def build_ledger() -> dict:
    db = CardDB.load()
    defs = load_chain_defs()
    # load_chain_defs strips _seed? No — it keeps entries verbatim (only top-level "_"
    # KEYS are dropped), so _seed provenance is readable here.
    overrides = _overrides()
    paths = sorted(FIXTURES.glob("*.trace.json.gz"))
    evidence, frames = trace_evidence(paths)

    today = _dt.date.today().isoformat()
    cards: dict[str, dict] = {}
    for cid, card in sorted(db.cards.items()):
        chains: dict[str, str] = {str(cid): chain_status(str(cid), defs, overrides,
                                                         evidence)}
        for aid in card.attacks:
            k = f"attack:{aid}"
            chains[k] = chain_status(k, defs, overrides, evidence)
        status = min(chains.values(), key=lambda s: _ORDER[s])
        ev = sorted(set().union(*(evidence.get(k, set()) for k in chains)))
        cards[str(cid)] = {"name": card.name, "cardType": _TYPE_NAME[card.cardType],
                           "status": status, "chains": chains,
                           "evidence": ev, "updated": today}

    # Interpreter-op conformance: which ops appear in a def exercised by a clean trace.
    from cgpy.chain import OPS
    covered_ops: set[str] = set()
    for chain_id in evidence:
        entry = defs.get(chain_id)
        if entry:
            covered_ops |= ops_in(entry)
    covered_ops &= set(OPS)

    n_cards = len(cards)
    verified = sum(1 for c in cards.values() if c["status"] == "verified")
    summary = {
        "cards": {"verified": verified, "total": n_cards},
        "chains": dict(Counter(s for c in cards.values() for s in c["chains"].values())),
        "cleanFrames": {"clean": frames["total"], "total": frames["total"],
                        "note": "committed fixtures are green by the CI parity gate"},
        "ops": {"covered": len(covered_ops), "total": len(OPS),
                "nativeChainVocabulary": 71,
                "coveredOps": sorted(covered_ops)},
        "traces": len(paths),
    }
    return {"_meta": {"tool": "tools/parity/report.py", "updated": today,
                      "note": "per-chain coverage of the cgpy ChainDef pool (ADR-0050 "
                              "M4); statuses: verified > derived > seeded > unprobed > "
                              "deferred"},
            "summary": summary, "cards": cards}


def rollup(ledger: dict) -> str:
    s = ledger["summary"]
    lines = [f"cards verified: {s['cards']['verified']}/{s['cards']['total']}",
             f"chains by status: " + ", ".join(
                 f"{k}={v}" for k, v in sorted(s["chains"].items(),
                                               key=lambda kv: -_ORDER.get(kv[0], 0))),
             f"clean frames: {s['cleanFrames']['clean']}/{s['cleanFrames']['total']} "
             f"across {s['traces']} committed traces",
             f"interpreter ops trace-covered: {s['ops']['covered']}/{s['ops']['total']} "
             f"(native Chain vocabulary: {s['ops']['nativeChainVocabulary']})"]
    by = Counter()
    for c in ledger["cards"].values():
        by[(c["cardType"], c["status"])] += 1
    lines.append("card status x type:")
    for ct in sorted({k[0] for k in by}):
        row = {st: by.get((ct, st), 0)
               for st in ("verified", "derived", "seeded", "unprobed", "deferred")}
        lines.append(f"  {ct:<15}" + "  ".join(f"{k}={v}" for k, v in row.items() if v))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cgpy coverage ledger + rollup (M4).")
    ap.add_argument("--print", action="store_true", help="rollup only, no ledger write")
    args = ap.parse_args(argv)
    ledger = build_ledger()
    print(rollup(ledger))
    if not args.print:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
        print(f"\nwrote {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
