"""Snapshot the native engine's card/attack tables into committed cgpy data (ADR-0050).

cgpy must run with no DLL, so the engine's `AllCard()` / `AllAttack()` JSON is dumped once into
`src/cgpy/defs/{card_data,attack_data}.json` (canonical form: sorted keys, LF, utf-8) plus a
`tables_meta.json` sidecar recording the source binaries' sha256 — a staleness check if the
competition ever ships a new engine build.

It also probes `BattleStart` deck validation with deliberately malformed decks and pins the
native `errorPlayer`/`errorType` codes into `validation_probes.json`, so cgpy's deck validation
can reproduce them exactly rather than guess.

Usage (needs the DLL — dev box or a runner with src/cg present):
    python tools/parity/snapshot_tables.py
    python tools/parity/snapshot_tables.py --check   # exit 1 if the DLL and snapshot disagree
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFS = REPO / "src" / "cgpy" / "defs"

sys.path.insert(0, str(REPO / "src"))


def _canonical(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def _load_tables() -> tuple[list, list]:
    """The engine's card/attack tables as parsed JSON (requires the DLL)."""
    from cg.sim import lib

    cards = json.loads(lib.AllCard().decode())
    attacks = json.loads(lib.AllAttack().decode())
    return cards, attacks


def _lib_hashes() -> dict:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ((REPO / "src" / "cg" / "cg.dll"), (REPO / "src" / "cg" / "libcg.so"))
        if p.exists()
    }


def _probe_validation(cards: list) -> dict:
    """Pin BattleStart's deck-validation verdicts (errorPlayer/errorType) for malformed decks.

    Each probe seats the malformed deck as deck0 against a known-legal deck1, then re-checks a
    legal/legal control. `battle_finish` frees whatever the engine allocated.
    """
    from cg.game import battle_finish, battle_start

    by_id = {c["cardId"]: c for c in cards}
    basics = [c for c in cards if c.get("basic") and c["cardType"] == 0]
    basic_id = basics[0]["cardId"]
    other_basic = basics[1]["cardId"]
    energy_id = next(c["cardId"] for c in cards if c["cardType"] == 5)  # a Basic Energy
    non_basic_pokemon = next(c["cardId"] for c in cards
                             if c["cardType"] == 0 and not c.get("basic"))
    ace_specs = [c["cardId"] for c in cards if c.get("aceSpec")]

    legal = [basic_id] * 4 + [other_basic] * 4 + [energy_id] * 52

    def probe(deck0: list[int]) -> dict:
        obs, start = battle_start(list(deck0), list(legal))
        verdict = {"errorPlayer": start.errorPlayer, "errorType": start.errorType,
                   "started": obs is not None}
        battle_finish()
        return verdict

    probes = {
        "legal_control": {"deck": "4x basicA + 4x basicB + 52x energy", "result": probe(legal)},
        "five_copies_of_a_name": {
            "deck": f"5x {by_id[basic_id]['name']}",
            "result": probe([basic_id] * 5 + [other_basic] * 4 + [energy_id] * 51),
        },
        "no_basic_pokemon": {
            "deck": "60x energy",
            "result": probe([energy_id] * 60),
        },
        "only_evolution_pokemon": {
            "deck": "4x a non-basic Pokemon + 56x energy",
            "result": probe([non_basic_pokemon] * 4 + [energy_id] * 56),
        },
        "unknown_card_id": {
            "deck": "one id 999999",
            "result": probe([999999] + [basic_id] * 4 + [energy_id] * 55),
        },
    }
    if len(ace_specs) >= 2:
        probes["two_ace_specs"] = {
            "deck": "2 distinct ACE SPEC cards",
            "result": probe(ace_specs[:2] + [basic_id] * 4 + [energy_id] * 54),
        }
        probes["duplicate_ace_spec"] = {
            "deck": "2x the same ACE SPEC",
            "result": probe([ace_specs[0]] * 2 + [basic_id] * 4 + [energy_id] * 54),
        }
    return probes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Snapshot engine card/attack tables for cgpy.")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the live DLL tables differ from the committed snapshot")
    ap.add_argument("--skip-probes", action="store_true",
                    help="skip the BattleStart validation probes (tables only)")
    args = ap.parse_args(argv)

    cards, attacks = _load_tables()
    card_text = _canonical(cards)
    attack_text = _canonical(attacks)

    card_path = DEFS / "card_data.json"
    attack_path = DEFS / "attack_data.json"
    meta_path = DEFS / "tables_meta.json"

    if args.check:
        ok = True
        for path, fresh in ((card_path, card_text), (attack_path, attack_text)):
            if not path.exists() or path.read_text(encoding="utf-8") != fresh:
                print(f"snapshot drift: {path.name} differs from the live engine")
                ok = False
        print("snapshot check " + ("OK" if ok else "FAILED"))
        return 0 if ok else 1

    DEFS.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card_text, encoding="utf-8")
    attack_path.write_text(attack_text, encoding="utf-8")

    meta = {"source_sha256": _lib_hashes(),
            "cards": len(cards), "attacks": len(attacks)}
    if not args.skip_probes:
        meta["validation_probes"] = _probe_validation(cards)
    meta_path.write_text(_canonical(meta), encoding="utf-8")

    print(f"wrote {card_path.name} ({len(cards)} cards), {attack_path.name} "
          f"({len(attacks)} attacks), {meta_path.name}")
    if not args.skip_probes:
        for name, p in meta["validation_probes"].items():
            print(f"  probe {name}: {p['result']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
