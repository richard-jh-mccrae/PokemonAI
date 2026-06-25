"""Convert between a Limitless decklist (.txt) and the competition deck.csv.

Limitless lets you pick any *printing* of a card; the competition pool catalogs
each card under its own canonical printing, so the bridge is the card **name**,
not (set, number) — see ADR-0013. Energy basics are mapped by element
("Psychic Energy" -> Basic {P} Energy). Names are normalized for case, accents,
and straight/curly apostrophes.

`to-csv` resolves every line, asserts the 5 deck-construction rules, and writes
`my_submissions/agents/<name>/deck.csv` only if *everything* passes (hard-fail,
see ADR-0013). `to-txt` renders a deck.csv back to a Limitless-style .txt.

Usage:
    python tools/deck_convert.py to-csv <deck.txt> <dir-name> [--force]
    python tools/deck_convert.py to-txt <deck.csv> [-o out.txt]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))  # make `meta_tracker` importable

from meta_tracker.cards import load_cards, stage_rank  # noqa: E402

AGENTS = REPO / "my_submissions" / "agents"
EN_CSV = REPO / "data" / "EN_Card_Data.csv"

# basic-energy {symbol} -> element name
_SYMBOL = {"G": "Grass", "R": "Fire", "W": "Water", "L": "Lightning",
           "P": "Psychic", "F": "Fighting", "D": "Darkness", "M": "Metal"}

# card category -> Limitless section / trainer sub-order
_SECTION = {"pokemon": "Pokémon", "item": "Trainer", "tool": "Trainer",
            "supporter": "Trainer", "stadium": "Trainer",
            "basic_energy": "Energy", "special_energy": "Energy"}
_TRAINER_SUB = {"supporter": 0, "item": 1, "tool": 2, "stadium": 3}


class ConvertError(RuntimeError):
    """A conversion that can't proceed; ``.problems`` lists every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def norm(s: str) -> str:
    """Fold case, accents, whitespace, and curly->straight apostrophe for matching."""
    s = (s or "").replace("’", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


@lru_cache(maxsize=1)
def _load_en(path: str | None = None) -> dict[int, tuple[str, str, str]]:
    """``{id: (name, set, collection_no)}`` from EN_Card_Data (first row per id)."""
    out: dict[int, tuple[str, str, str]] = {}
    with open(path or EN_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cid = int(r["Card ID"])
            out.setdefault(cid, (r["Card Name"].strip(), r["Expansion"].strip(),
                                 r["Collection No."].strip()))
    return out


@lru_cache(maxsize=1)
def _indexes() -> tuple[dict[str, list[int]], dict[str, int], dict[int, str]]:
    """(name->ids, element-energy-name->id, basic-energy-id->element)."""
    cards = load_cards()
    by_norm: dict[str, list[int]] = defaultdict(list)
    elem_to_id: dict[str, int] = {}
    id_to_elem: dict[int, str] = {}
    for cid, c in cards.items():
        by_norm[norm(c["name"])].append(cid)
        if c.get("category") == "basic_energy":
            m = re.search(r"\{(\w)\}", c["name"])
            if m and m.group(1) in _SYMBOL:
                el = _SYMBOL[m.group(1)]
                elem_to_id[norm(f"{el} Energy")] = cid
                id_to_elem[cid] = el
    for ids in by_norm.values():
        ids.sort()
    return dict(by_norm), elem_to_id, id_to_elem


# --- forward: .txt -> ids -------------------------------------------------

def _split_card(toks: list[str]) -> tuple[int, str, str | None, str | None]:
    """`4 Dreepy TWM 128` -> (4, 'Dreepy', 'TWM', '128'); set/number optional."""
    count = int(toks[0])
    rest = toks[1:]
    sett = num = None
    if (len(rest) >= 3 and re.fullmatch(r"[A-Z]{2,4}", rest[-2])
            and re.fullmatch(r"\d+[a-zA-Z]?", rest[-1])):
        sett, num, rest = rest[-2], rest[-1], rest[:-2]
    return count, " ".join(rest), sett, num


def _resolve(name: str, sett: str | None, num: str | None) -> tuple[int | None, str | None]:
    by_norm, elem_to_id, _ = _indexes()
    en = _load_en()
    nn = norm(name)
    if nn in elem_to_id:                       # basic energy, by element
        return elem_to_id[nn], None
    ids = by_norm.get(nn)
    if not ids:
        return None, f"absent from pool: {name!r} ({sett} {num})"
    if len(ids) == 1:
        return ids[0], None
    hit = [i for i in ids if en.get(i, (None, None, None))[1:] == (sett, num)]
    if len(hit) == 1:                          # disambiguate by the printing
        return hit[0], None
    return None, f"ambiguous: {name!r} -> ids {ids}; printing {sett} {num} matched {len(hit)}"


def resolve_deck(text: str) -> tuple[list[int], list[str]]:
    """Parse a Limitless .txt into an expanded id list + a list of problems."""
    deck: list[int] = []
    problems: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        toks = line.split()
        if not toks[0].isdigit():              # section header e.g. "Pokémon: 19"
            continue
        count, name, sett, num = _split_card(toks)
        cid, err = _resolve(name, sett, num)
        if err:
            problems.append(err)
        else:
            deck.extend([cid] * count)
    return deck, problems


# --- legality -------------------------------------------------------------

def check_legality(deck: list[int]) -> list[str]:
    """Return every construction-rule violation (empty list == legal)."""
    cards = load_cards()
    v: list[str] = []
    if len(deck) != 60:
        v.append(f"deck has {len(deck)} cards, must be exactly 60")

    by_name: dict[str, list] = {}            # name -> [count, category]
    for cid in deck:
        c = cards.get(cid, {})
        e = by_name.setdefault(c.get("name", str(cid)), [0, c.get("category")])
        e[0] += 1
    for name, (k, cat) in by_name.items():
        if cat != "basic_energy" and k > 4:
            v.append(f"{k}x {name} — max 4 copies (only basic energy is unlimited)")

    ace = sum(1 for cid in deck if cards.get(cid, {}).get("aceSpec"))
    if ace > 1:
        v.append(f"{ace} ACE SPEC cards — max 1 per deck")

    if not any(cards.get(cid, {}).get("category") == "pokemon"
               and cards.get(cid, {}).get("stage") == "basic" for cid in deck):
        v.append("no Basic Pokémon — a deck needs at least 1")
    return v


# --- reverse: ids -> .txt -------------------------------------------------

def render_txt(deck: list[int]) -> str:
    """Render an id list as a Limitless-style decklist (Pokémon evolution-grouped)."""
    cards = load_cards()
    en = _load_en()
    _, _, id_to_elem = _indexes()
    poke, trainer, energy = [], [], []
    for cid, k in Counter(deck).items():
        c = cards.get(cid, {})
        name, sett, num = en.get(cid, (c.get("name", str(cid)), "", ""))
        cat = c.get("category", "item")
        if cat == "basic_energy" and cid in id_to_elem:
            name = f"{id_to_elem[cid]} Energy"
        sec = _SECTION.get(cat, "Trainer")
        if sec == "Pokémon":
            poke.append({"k": k, "name": name, "set": sett, "num": num,
                         "rank": stage_rank(c), "evo": norm(c.get("evolvesFrom") or ""),
                         "nn": norm(c.get("name") or name)})
        elif sec == "Energy":
            energy.append((-k, name, k, sett, num))
        else:
            trainer.append((_TRAINER_SUB.get(cat, 9), -k, name, k, sett, num))

    # group Pokémon into evolution lines: basic -> stage1 -> stage2, kept together
    node = {}
    for n in poke:
        node.setdefault(n["nn"], n)

    def root(n: dict) -> str:
        cur, seen = n, set()
        while cur["evo"] and cur["evo"] in node and cur["nn"] not in seen:
            seen.add(cur["nn"])
            cur = node[cur["evo"]]
        return cur["nn"]

    lines: dict[str, list] = defaultdict(list)
    for n in poke:
        lines[root(n)].append(n)
    poke_out = []
    ordered = sorted(lines.values(),
                     key=lambda ms: (-sum(m["k"] for m in ms),
                                     min(ms, key=lambda m: m["rank"])["name"]))
    for members in ordered:
        for m in sorted(members, key=lambda m: (m["rank"], m["name"])):
            poke_out.append((m["k"], m["name"], m["set"], m["num"]))

    sections = [
        ("Pokémon", poke_out),
        ("Trainer", [(k, nm, s, c) for _, _, nm, k, s, c in sorted(trainer)]),
        ("Energy", [(k, nm, s, c) for _, nm, k, s, c in sorted(energy)]),
    ]
    out: list[str] = []
    for label, rows in sections:
        if not rows:
            continue
        out.append(f"{label}: {sum(k for k, *_ in rows)}")
        for k, name, sett, num in rows:
            out.append(f"{k} {name}" + (f" {sett} {num}" if sett else ""))
        out.append("")
    return "\n".join(out).strip() + "\n"


# --- orchestration --------------------------------------------------------

def convert_to_csv(txt_path, name: str, *, force: bool = False,
                   dest_root: Path = AGENTS) -> Path:
    """Resolve + validate a Limitless .txt, then write agents/<name>/deck.csv."""
    deck, problems = resolve_deck(Path(txt_path).read_text(encoding="utf-8"))
    if problems:
        raise ConvertError(problems)
    violations = check_legality(deck)
    if violations:
        raise ConvertError(violations)
    dest = Path(dest_root) / name
    if dest.exists() and not force:
        raise ConvertError([f"{dest} already exists; pass --force to overwrite"])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "deck.csv").write_text("\n".join(str(c) for c in sorted(deck)) + "\n",
                                   encoding="utf-8")
    return dest


def convert_to_txt(deck_csv) -> str:
    ids = [int(x) for x in Path(deck_csv).read_text(encoding="utf-8").split()]
    return render_txt(ids)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("to-csv", help="Limitless .txt -> agents/<name>/deck.csv")
    a.add_argument("txt"); a.add_argument("name")
    a.add_argument("--force", action="store_true", help="overwrite if the dir exists")
    b = sub.add_parser("to-txt", help="deck.csv -> Limitless .txt (stdout)")
    b.add_argument("deck"); b.add_argument("-o", "--out", help="write to a file instead of stdout")
    args = ap.parse_args()

    if args.cmd == "to-csv":
        try:
            dest = convert_to_csv(args.txt, args.name, force=args.force)
        except ConvertError as e:
            print(f"deck_convert: cannot build deck ({len(e.problems)} problem(s)):", file=sys.stderr)
            for p in e.problems:
                print(f"  - {p}", file=sys.stderr)
            raise SystemExit(1)
        print(f"wrote 60 cards -> {dest / 'deck.csv'}")
    else:
        txt = convert_to_txt(args.deck)
        if args.out:
            Path(args.out).write_text(txt, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            sys.stdout.write(txt)


if __name__ == "__main__":
    main()
