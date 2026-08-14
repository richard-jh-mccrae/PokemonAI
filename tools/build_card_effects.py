"""Build the shipped Effect-Clause artifact from measured and authored sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meta_tracker.card_effects import apply_overrides


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "src" / "common" / "card_effects.json"
DEFAULT_OVERRIDES = REPO / "tools" / "meta_tracker" / "effect_overrides.json"
DEFAULT_MEASURED = REPO / "tools" / "meta_tracker" / "measured_effects.json"


def render(measured, overrides) -> bytes:
    table = {int(key): value for key, value in measured.items() if str(key).isdigit()}
    authored = {int(key): value for key, value in overrides.items() if str(key).isdigit()}
    merged = apply_overrides(table, authored)
    payload = {"_covers": overrides.get("_covers", measured.get("_covers", {}))}
    payload.update({str(card_id): clauses for card_id, clauses in sorted(merged.items())})
    return json.dumps(payload, ensure_ascii=False, indent=0).encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--measured", type=Path, default=DEFAULT_MEASURED)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    measured = json.loads(args.measured.read_text(encoding="utf-8"))
    overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    generated = render(measured, overrides)
    if args.check:
        return 0 if args.out.read_bytes() == generated else 1
    args.out.write_bytes(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
