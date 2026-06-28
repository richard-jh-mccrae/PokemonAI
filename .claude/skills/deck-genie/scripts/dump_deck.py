"""Dump a deck's authoritative card facts — the substrate for deck-genie Phase 1.

Joins the agent's `deck.csv` (card ids) to the engine's ground-truth `CardData` /
`Attack` tables (`cg.api`) and the shipped behavioral `card_functions.json` tags, then
renders a category-organised overview. The engine is the source of truth for HP /
weakness / energy cost / attack text (the committed `cards.json` is stale — see
docs/card-functions.md), so never hand-transcribe these.

Usage (from anywhere in the repo):
    python .claude/skills/deck-genie/scripts/dump_deck.py mega_starmie
    python .claude/skills/deck-genie/scripts/dump_deck.py mega_starmie --json   # machine form
    python .claude/skills/deck-genie/scripts/dump_deck.py --deck-dir src/agents/mega_starmie

Prints Markdown to stdout. `--json` emits the same data as JSON for downstream tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _find_repo(start: Path) -> Path:
    """Walk up from `start` (and this file) until a dir holding `src/cg/api.py` is found."""
    for base in (start, Path(__file__).resolve()):
        for parent in [base, *base.parents]:
            if (parent / "src" / "cg" / "api.py").exists():
                return parent
    raise SystemExit("could not locate repo root (no src/cg/api.py above cwd or script)")


def _energy_name(et) -> str:
    from cg.api import EnergyType
    if et is None:
        return "-"
    try:
        return EnergyType(et).name.title()
    except ValueError:
        return str(et)


def _category(cd) -> str:
    """Human bucket: Pokémon / Supporter / Item / Tool / Stadium / Energy."""
    from cg.api import CardType
    return {
        CardType.POKEMON: "Pokémon",
        CardType.ITEM: "Item",
        CardType.TOOL: "Tool",
        CardType.SUPPORTER: "Supporter",
        CardType.STADIUM: "Stadium",
        CardType.BASIC_ENERGY: "Energy",
        CardType.SPECIAL_ENERGY: "Energy",
    }.get(CardType(cd.cardType), str(cd.cardType))


def _stage(cd) -> str:
    if cd.megaEx:
        return "Mega ex"
    if cd.basic:
        return "Basic"
    if cd.stage1:
        return "Stage 1"
    if cd.stage2:
        return "Stage 2"
    return ""


def _prize_value(cd) -> int:
    if cd.megaEx:
        return 3
    if cd.ex:
        return 2
    return 1


def build_records(deck_dir: Path, repo: Path) -> list[dict]:
    """One record per UNIQUE card id in deck.csv (deck order preserved), with engine
    facts + behavioral tags + deck count."""
    from cg.api import all_attack, all_card_data

    ids = [int(x) for x in (deck_dir / "deck.csv").read_text(encoding="utf-8").split() if x.strip()]
    counts = Counter(ids)
    seen, order = set(), []
    for cid in ids:                       # de-dup, keep first-seen order
        if cid not in seen:
            seen.add(cid)
            order.append(cid)

    cards = {c.cardId: c for c in all_card_data()}
    attacks = {a.attackId: a for a in all_attack()}
    fn_path = repo / "src" / "common" / "card_functions.json"
    tags = json.loads(fn_path.read_text(encoding="utf-8")) if fn_path.exists() else {}

    records = []
    for cid in order:
        cd = cards.get(cid)
        if cd is None:
            records.append({"id": cid, "count": counts[cid], "name": f"<unknown id {cid}>",
                            "category": "?", "tags": tags.get(str(cid), [])})
            continue
        rec = {
            "id": cid,
            "count": counts[cid],
            "name": cd.name,
            "category": _category(cd),
            "stage": _stage(cd),
            "hp": cd.hp,
            "ex": cd.ex, "megaEx": cd.megaEx, "tera": cd.tera, "aceSpec": cd.aceSpec,
            "prize_value": _prize_value(cd) if cd.hp > 0 else 0,
            "type": _energy_name(cd.energyType) if cd.hp > 0 or cd.energyType else "-",
            "weakness": _energy_name(cd.weakness),
            "resistance": _energy_name(cd.resistance),
            "retreat": cd.retreatCost,
            "evolvesFrom": cd.evolvesFrom,
            "abilities": [{"name": s.name, "text": s.text} for s in cd.skills],
            "attacks": [
                {"name": a.name, "damage": a.damage,
                 "cost": [_energy_name(e) for e in a.energies], "text": a.text}
                for a in (attacks[aid] for aid in cd.attacks if aid in attacks)
            ],
            "tags": tags.get(str(cid), []),
        }
        records.append(rec)
    return records


def _fmt_cost(cost: list[str]) -> str:
    return "".join(c[0] for c in cost) if cost else "—"   # WWW / CC / — (free)


def render_markdown(records: list[dict], deck_dir: Path) -> str:
    out: list[str] = []
    name = deck_dir.name
    total = sum(r["count"] for r in records)
    out.append(f"# Deck facts — `{name}` ({total} cards, {len(records)} unique)\n")

    txt = deck_dir / "deck.txt"
    if txt.exists():
        out.append("## Decklist (deck.txt)\n```\n" + txt.read_text(encoding="utf-8").strip() + "\n```\n")

    buckets = ["Pokémon", "Supporter", "Item", "Tool", "Stadium", "Energy", "?"]
    by_cat: dict[str, list[dict]] = {b: [] for b in buckets}
    for r in records:
        by_cat.setdefault(r.get("category", "?"), []).append(r)

    # --- Pokémon: full detail (attacks/abilities/stats) ---
    mons = by_cat.get("Pokémon", [])
    if mons:
        out.append("## Pokémon\n")
        for r in mons:
            flags = " ".join(f for f, on in
                             [("ex", r.get("ex")), ("Mega-ex", r.get("megaEx")),
                              ("Tera", r.get("tera"))] if on)
            head = (f"### {r['count']}× {r['name']}  —  {r.get('stage','')} "
                    f"{r.get('type','')} · {r.get('hp','?')} HP · {r['prize_value']} prize"
                    + (f" · {flags}" if flags else ""))
            out.append(head)
            line = (f"- weakness **{r.get('weakness','-')}** · resist {r.get('resistance','-')} "
                    f"· retreat {r.get('retreat','?')}")
            if r.get("evolvesFrom"):
                line += f" · evolves from **{r['evolvesFrom']}**"
            out.append(line)
            if r.get("tags"):
                out.append(f"- function tags: `{'`, `'.join(r['tags'])}`")
            for ab in r.get("abilities", []):
                out.append(f"- **Ability — {ab['name']}:** {ab['text']}")
            for a in r.get("attacks", []):
                out.append(f"- **{_fmt_cost(a['cost'])} — {a['name']}** "
                           f"({a['damage']}): {a['text']}")
            out.append("")

    # --- Trainers + Energy: compact rows (name · count · tags · text) ---
    for cat in ("Supporter", "Item", "Tool", "Stadium", "Energy"):
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        out.append(f"## {cat}\n")
        for r in rows:
            tagstr = f" · `{'`, `'.join(r['tags'])}`" if r.get("tags") else ""
            text = ""
            ab = r.get("abilities") or []
            if ab:
                text = " — " + " / ".join(s["text"] for s in ab)
            elif cat == "Energy":
                text = f" — provides {r.get('type','?')}"
            out.append(f"- **{r['count']}× {r['name']}**{tagstr}{text}")
        out.append("")

    unknown = by_cat.get("?", [])
    if unknown:
        out.append("## Unresolved ids (not in engine card table)\n")
        for r in unknown:
            out.append(f"- {r['count']}× id {r['id']}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump a deck's authoritative card facts.")
    ap.add_argument("deck", nargs="?", help="agent name under src/agents/ (e.g. mega_starmie)")
    ap.add_argument("--deck-dir", help="explicit path to an agent dir (overrides `deck`)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    args = ap.parse_args()

    # Pokémon names carry é / × / {W}; force UTF-8 so piping never dies on a cp1252 console.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    repo = _find_repo(Path.cwd())
    sys.path.insert(0, str(repo / "src"))

    if args.deck_dir:
        deck_dir = Path(args.deck_dir).resolve()
    elif args.deck:
        deck_dir = repo / "src" / "agents" / args.deck
    else:
        ap.error("give an agent name or --deck-dir")
    if not (deck_dir / "deck.csv").exists():
        raise SystemExit(f"no deck.csv in {deck_dir}")

    records = build_records(deck_dir, repo)
    if args.json:
        print(json.dumps({"deck": deck_dir.name, "cards": records}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(records, deck_dir))


if __name__ == "__main__":
    main()
