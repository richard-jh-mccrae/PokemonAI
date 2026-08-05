"""Validate a Matchup Brief JSON — the deterministic Phase-B gate for /matchup-genie (ADR-0027).

Checks the Brief shape, that `covers` is non-empty (and matches the deck export's index.json), that
every `threat`/`target` card actually appears in the opponent deck (the analogue of deck-genie's
per-Hypothesis trigger checks — catches typos / hallucinated cards), that `target` roles are legal, and
that every `opponent_properties` key is registered in src/common/scouting/opponent_properties.json.

Hard failures exit 1; warnings are printed but pass. Usage (from anywhere in the repo):
    python .claude/skills/matchup-genie/scripts/validate_brief.py <slug>
    python .claude/skills/matchup-genie/scripts/validate_brief.py <slug> --brief path.json --deck-dir dir --index index.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TARGET_ROLES_FALLBACK = {"prize_liability", "fragile_preevo", "disruption_target", "attacker",
                          "enabler", "engine", "support", "unknown", "avoid"}
_REQUIRED = ("slug", "label", "covers", "authored", "summary", "opponent_properties", "threats", "targets")


def _target_roles(repo: Path) -> set[str]:
    """Legal `target` roles, sourced from the Brief schema's role enum so this list can never drift
    from src/common/scouting/brief.schema.json (ADR-0051 added `disruption_target` / `avoid` there but
    this hardcoded set was missed — the drift that would have rejected an enriched Brief). Falls back
    to the known set if the schema can't be read."""
    try:
        schema = json.loads((repo / "src" / "common" / "scouting" / "brief.schema.json").read_text(encoding="utf-8"))
        enum = schema["properties"]["targets"]["items"]["properties"]["role"]["enum"]
        return set(enum) or set(_TARGET_ROLES_FALLBACK)
    except (OSError, KeyError, json.JSONDecodeError):
        return set(_TARGET_ROLES_FALLBACK)


def _find_repo(start: Path) -> Path:
    for base in (start, Path(__file__).resolve()):
        for parent in [base, *base.parents]:
            if (parent / "src" / "cg" / "api.py").exists():
                return parent
    raise SystemExit("could not locate repo root (no src/cg/api.py above cwd or script)")


def _norm(s: str) -> str:
    """Fold case/accents/whitespace/curly-apostrophe for name matching (mirrors deck_convert.norm)."""
    import unicodedata
    s = (s or "").replace("’", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _deck_names(deck_dir: Path, repo: Path) -> set[str] | None:
    """Normalized card names in deck.csv, or None if the deck can't be read (warn, skip card checks)."""
    csv = deck_dir / "deck.csv"
    if not csv.exists():
        return None
    sys.path.insert(0, str(repo / "tools"))
    from meta_tracker.cards import load_cards
    cards = load_cards()
    ids = [int(x) for x in csv.read_text(encoding="utf-8").split() if x.strip()]
    return {_norm(cards.get(cid, {}).get("name", "")) for cid in ids} - {""}


def validate(slug: str, brief_path: Path, deck_dir: Path, index_path: Path,
             repo: Path) -> tuple[list[str], list[str]]:
    """Return (hard_problems, warnings)."""
    problems: list[str] = []
    warnings: list[str] = []
    target_roles = _target_roles(repo)

    if not brief_path.exists():
        return ([f"brief not found: {brief_path}"], warnings)
    try:
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ([f"brief is not valid JSON: {e}"], warnings)

    # --- required fields + types ---
    for k in _REQUIRED:
        if k not in brief:
            problems.append(f"missing required field: {k!r}")
    if brief.get("slug") != slug:
        problems.append(f"slug field {brief.get('slug')!r} != {slug!r} (the filename)")

    covers = brief.get("covers")
    if not isinstance(covers, list) or not covers or not all(isinstance(c, str) for c in covers):
        problems.append("covers must be a non-empty list of strings")
    if "tempo" in brief and brief["tempo"] not in {"fast", "midrange", "slow"}:
        problems.append(f"tempo {brief['tempo']!r} not in fast|midrange|slow")

    # --- covers vs the deck export index (warn only — the meta regenerates) ---
    if index_path.exists():
        try:
            entry = next((e for e in json.loads(index_path.read_text(encoding="utf-8"))
                          if e.get("slug") == slug), None)
        except json.JSONDecodeError:
            entry = None
        if entry is None:
            warnings.append(f"slug {slug!r} not in {index_path.name} — regenerate the export or check the slug")
        elif isinstance(covers, list) and sorted(covers) != sorted(entry.get("covers", [])):
            warnings.append(f"covers diverge from {index_path.name}: brief={sorted(covers)} index={sorted(entry.get('covers', []))}")
    else:
        warnings.append(f"no {index_path} — skipped covers cross-check")

    # --- covers collision vs every OTHER shipped Brief (ADR-0038 hardening): match_brief routes an
    # archetype to the alphabetically-FIRST covering Brief, so an overlap misroutes SILENTLY ---
    if isinstance(covers, list) and brief_path.parent.is_dir():
        for other in sorted(brief_path.parent.glob("*.json")):
            if other.name == brief_path.name:
                continue
            try:
                oc = json.loads(other.read_text(encoding="utf-8")).get("covers", [])
            except json.JSONDecodeError:
                continue
            clash = sorted(set(covers) & set(oc))
            if clash:
                problems.append(f"covers collide with {other.name}: {clash} — every archetype string "
                                f"must route to exactly ONE Brief (match_brief takes the first)")

    # --- threats / targets reference real cards in the deck ---
    names = _deck_names(deck_dir, repo)
    if names is None:
        warnings.append(f"no deck.csv in {deck_dir} — skipped threat/target card checks")

    for t in brief.get("threats", []) or []:
        if not isinstance(t, dict) or "card" not in t or "why" not in t:
            problems.append(f"threat entry must have card+why: {t!r}"); continue
        if names is not None and _norm(t["card"]) not in names:
            problems.append(f"threat card not in the deck: {t['card']!r}")

    for t in brief.get("targets", []) or []:
        if not isinstance(t, dict) or not {"card", "role", "why"} <= set(t):
            problems.append(f"target entry must have card+role+why: {t!r}"); continue
        if t["role"] not in target_roles:
            problems.append(f"target {t['card']!r} role {t['role']!r} not in {sorted(target_roles)}")
        if names is not None and _norm(t["card"]) not in names:
            problems.append(f"target card not in the deck: {t['card']!r}")

    # --- opponent_properties keys registered + typed ---
    reg = json.loads((repo / "src" / "common" / "scouting" / "opponent_properties.json").read_text(encoding="utf-8")).get("properties", {})
    props = brief.get("opponent_properties", {})
    if not isinstance(props, dict):
        problems.append("opponent_properties must be an object")
    else:
        for key, val in props.items():
            spec = reg.get(key)
            if spec is None:
                warnings.append(f"opponent_properties key {key!r} not registered — add it to "
                                f"src/common/scouting/opponent_properties.json (consumer:'unwired') and flag it")
                continue
            typ = spec.get("type")
            if typ == "bool" and not isinstance(val, bool):
                problems.append(f"opponent_properties {key!r} must be bool, got {val!r}")
            elif typ == "enum" and val not in spec.get("values", []):
                problems.append(f"opponent_properties {key!r}={val!r} not in {spec.get('values', [])}")
            elif typ == "number" and not isinstance(val, (int, float)):
                problems.append(f"opponent_properties {key!r} must be a number, got {val!r}")

    return (problems, warnings)


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate a Matchup Brief JSON (ADR-0027).")
    ap.add_argument("slug", help="matchup slug (dir under data/meta/decks/ and briefs/<slug>.json)")
    ap.add_argument("--brief", help="override briefs/<slug>.json path")
    ap.add_argument("--deck-dir", help="override data/meta/decks/<slug> path")
    ap.add_argument("--index", help="override data/meta/decks/index.json path")
    args = ap.parse_args()

    repo = _find_repo(Path.cwd())
    brief_path = Path(args.brief) if args.brief else repo / "src" / "common" / "scouting" / "briefs" / f"{args.slug}.json"
    deck_dir = Path(args.deck_dir) if args.deck_dir else repo / "data" / "meta" / "decks" / args.slug
    index_path = Path(args.index) if args.index else repo / "data" / "meta" / "decks" / "index.json"

    problems, warnings = validate(args.slug, brief_path, deck_dir, index_path, repo)

    for w in warnings:
        print(f"  ! warn: {w}")
    if problems:
        print(f"\nBrief INVALID ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print(f"\nBrief OK: {args.slug}" + (f"  ({len(warnings)} warning(s))" if warnings else ""))


if __name__ == "__main__":
    main()
