"""Snipe the real / developing attacker (blunder-buster ms cluster), each behind a distinct signal:

- **f75/f47** — chip a benched forward-evolution WINCON pre-evo (Riolu→Mega Lucario ex) via
  `snipe-the-evolving-threat`, gated by `target_forward_form_in_play` so it stands down when the evolved
  wincon is already on the opponent's board (the ADR-0044 discriminator).
- **f39** — deny an ENERGIZED off-Prize-Path attacker while I still hold many prizes (`_SNIPE_THREAT_PRIZE_FLOOR`).
- **f85** — Alakazam's threat is CALCULATED from the opponent's hand size (`handSizeDamage x handCount`),
  so Kadabra→Alakazam becomes the strongest forward and is sniped over a bulky support line.

Fixtured through the shipped engine-backed Pilot (`decide()`), the strict retest bar. f75 snipes a Riolu
(a duplicate species) so it matches by card id, not exact index.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


@pytest.mark.req("REQ-READ-0006")
@pytest.mark.parametrize("fixture,by_card_id", [
    ("ms_snipe_evolving_wincon_preevo_f75.json", True),    # snipes a Riolu (duplicate species)
    ("ms_snipe_riolu_over_lunatone_f47.json", False),      # Riolu over the forced-promotion Lunatone
    ("ms_snipe_energized_bench_f39.json", False),          # the energized ex, at 6 prizes remaining
    ("ms_snipe_attacker_line_over_support_f85.json", False),  # Kadabra (Alakazam line) over Dudunsparce
])
def test_snipes_the_real_attacker(fixture, by_card_id):
    fx = _fx(fixture)
    dec = _shipped_pilot().explain(fx["obs"])
    chosen, correct = dec.chosen, fx["correct"]
    if by_card_id:                                          # duplicate species → match the card, not the slot
        cid = {t.index: t.card_id for t in dec.options}
        assert {cid.get(i) for i in correct} & {cid.get(i) for i in chosen}, (
            f"{fixture}: chose {chosen} (cards { {cid.get(i) for i in chosen} }), "
            f"want a {fx.get('correct_label')}")
    else:
        assert all(c in chosen for c in correct), f"{fixture}: chose {chosen}, want {correct} ({fx.get('correct_label')})"
