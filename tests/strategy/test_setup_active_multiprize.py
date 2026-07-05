"""The PREGAME setup-ACTIVE multi-prize demotion (residual-blunder audit 2026-07-05).

`dont-open-multiprize-active` (−15) — at `_SETUP_ACTIVE` a non-wincon multi-prize ex (Meowth ex, a
2-prize liability) scores negative, so a plain startable Basic (score 0) out-ranks it and takes the
Active Spot instead. The Active-pick sibling of `dont-pre-bench-the-supporter-tutor` (the pregame
BENCH decline): mega_lucario was opening Meowth ex ~4/25 self-play games, stranding a 2-prize
liability in the most-exposed slot AND forfeiting Last-Ditch Catch (which only triggers on an
IN-GAME bench-from-hand).

The demotion never strands the game: SETUP_ACTIVE is a forced single pick (minCount 1), so when the
ex is the ONLY startable Basic it stays the max-scoring option and is still placed; the `_WINCON_ROLES`
escape keeps a deck that MEANS to open its Basic-ex attacker free to do so.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.cards import CardFunctions  # noqa: E402
from common.pilot import Pilot  # noqa: E402
from common.scouting.provider import CardStat  # noqa: E402
from common.strategy import Strategy  # noqa: E402
from common.strategy.context import _SETUP_ACTIVE  # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY  # noqa: E402

MEOWTH, RIOLU = 1071, 677


def _build_mega_lucario_pilot():
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_lucario")
    return pilot


def _setup_active_obs(hand_ids):
    """A minimal SETUP_ACTIVE select (minCount 1, maxCount 1) offering each hand card as the Active."""
    opts = [{"type": "Card", "area": 2, "index": i, "playerIndex": 0} for i in range(len(hand_ids))]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_ACTIVE, "minCount": 1, "maxCount": 1, "option": opts}}


@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_opens_the_plain_basic_over_meowth_ex():
    """REQ-OPEN-0002: the real shipped mega_lucario Pilot picks Riolu (option 1) over Meowth ex
    (option 0) at the pregame Active pick — the residual blunder is resolved through the live decide()."""
    pilot = _build_mega_lucario_pilot()
    assert pilot.decide(_setup_active_obs([MEOWTH, RIOLU])) == [1], "should open Riolu, not Meowth ex"


@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_still_opens_meowth_when_it_is_the_only_basic():
    """REQ-OPEN-0002: the demotion is not a ban — a lone Meowth ex is a forced single pick, so it
    still takes the Active Spot (decide()'s take-fewer never trims a minCount-1 select)."""
    pilot = _build_mega_lucario_pilot()
    assert pilot.decide(_setup_active_obs([MEOWTH])) == [0], "a lone Basic must still be placed Active"


def test_general_rule_demotes_a_multiprize_ex_deck_agnostically():
    """The rule is deck-agnostic: a synthetic Pilot with only the general strategy still opens the
    plain Basic over an unroled multi-prize ex, and still forces the ex when it is alone."""
    stats = {MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80)}
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=CardFunctions({}))
    assert pilot.decide(_setup_active_obs([MEOWTH, RIOLU])) == [1]   # plain Basic out-ranks the ex
    assert pilot.decide(_setup_active_obs([RIOLU, MEOWTH])) == [0]   # order-independent (Riolu at opt 0)
    assert pilot.decide(_setup_active_obs([MEOWTH])) == [0]          # forced when alone


def test_wincon_basic_ex_is_not_demoted():
    """The `_WINCON_ROLES` escape: a Basic ex the deck DECLARES its win-condition is NOT demoted, so
    an ex-attacker deck can still open its wincon (guards against over-firing on Meowth-shaped cards)."""
    stats = {MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80)}
    pilot = Pilot(Strategy(roles={MEOWTH: ["primary_attacker"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))
    # wincon ex at score 0 ties the plain Basic at score 0 -> index tie-break keeps option 0 (the ex)
    assert pilot.decide(_setup_active_obs([MEOWTH, RIOLU])) == [0], "a wincon Basic ex must not be demoted"
