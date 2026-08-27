from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src")]

from common.ledger.readiness import audit_readiness
from common.cards import card_store


def _deck_cards(names):
    store = card_store()
    card_ids = {
        int(value)
        for name in names
        for value in (REPO / "src" / "agents" / name / "deck.csv").read_text(
            encoding="utf-8").split()
    }
    return {card_id: store[card_id] for card_id in sorted(card_ids)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--warnings-as-errors", action="store_true")
    parser.add_argument("--decks", nargs="+")
    args = parser.parse_args(argv)
    report = audit_readiness(
        cards=None if args.decks is None else _deck_cards(args.decks))
    payload = report.as_dict()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print("PASS" if report.passed else "FAIL")
        for finding in report.findings:
            print(f"{finding.category}: {finding.subject}: {finding.detail}")
        for warning in report.warnings:
            print(f"WARNING {warning.category}: {warning.subject}: {warning.detail}")
    return 0 if report.passed and not (args.warnings_as_errors and report.warnings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
