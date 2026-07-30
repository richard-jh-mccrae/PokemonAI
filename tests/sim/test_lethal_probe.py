"""ADR-0050 Phase 2(C) — the follow-up-select probe. Engine-backed (imports ``cg``; skips if absent).

``probe_follow_ups`` drives a seeded fixture's first step through the engine and dumps every follow-up
select the policy reaches — its context, and each option's RESOLVED ``card_id`` / ``inPlayArea`` /
``inPlayIndex`` — so Phase-3 follow-up-steering hooks (tutor→the right Tool, play-Tool→Active) are
authored against real encodings rather than guessed. The f15 Petrel tutor is the worked example: its
menu must expose an option resolving to the deck-certain Air Balloon.
"""
import json
from pathlib import Path

import pytest

from lethal_helpers import require_cg

REPO = Path(__file__).resolve().parents[2]
_AIR_BALLOON = 1174


def _mega_lucario_pilot():
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    deck = [int(x) for x in (REPO / "src" / "agents" / "mega_lucario" / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider (ADR-0051): EngineCardStatProvider.attack() serves
    # the same audit-overridden build_attack_stats table the legacy kwargs used to duplicate
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


@pytest.mark.req("REQ-LETHAL-SEED-0006")
def test_probe_exposes_the_tutor_menu_encodings_after_petrel():
    """The probe walks the f15 Petrel cascade and surfaces the tutor select with a resolvable Air
    Balloon option — the encoding a Phase-3 'tutor a retreat Tool' hook is authored against."""
    require_cg()
    from sim.lethal_probe import probe_follow_ups
    obs = json.loads((REPO / "tests" / "fixtures" / "corrections"
                      / "ml_petrel_balloon_retreat_lethal_f15.json").read_text(encoding="utf-8"))["obs"]

    selects = probe_follow_ups(_mega_lucario_pilot(), obs, [0])   # [0] = Play Team Rocket's Petrel

    assert selects, "the probe reached at least one follow-up select"
    tutor = next((s for s in selects if s["context"] == 7), None)
    assert tutor is not None, "the Petrel tutor select was surfaced"
    card_ids = [o["card_id"] for o in tutor["options"]]
    assert _AIR_BALLOON in card_ids                               # the enabler, with a real encoding
    ab = next(o for o in tutor["options"] if o["card_id"] == _AIR_BALLOON)
    assert ab["type"] is not None and "index" in ab              # options carry usable encodings
