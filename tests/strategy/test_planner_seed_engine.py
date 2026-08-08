"""ADR-0050 Phase 1 — engine-backed proof that exact seeding closes the seeding gap. Imports ``cg``
(committed native lib, offline on Windows + Linux like ``test_planner_engine.py``); skips cleanly if
the lib is absent. The seeded fixtures carry ``search_begin_input`` + ``own_prizes`` (backfilled by
``tools/train/backfill_seed.py``), so no replay is needed at test time.

The seeding gap made concrete: driving the f15 Petrel tutor through the engine, the deck-certain Air
Balloon (id 1174) is REACHABLE under exact seeding and ABSENT under the old decklist prefix — the whole
reason the retreat-enabler lethal was un-verifiable. And an already-applied lethal (f110) still
confirms, so the fix is non-regressive.
"""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

pytest.importorskip("cg")

from cg import api as cgapi                                     # noqa: E402
from common.cards import CardFunctions                          # noqa: E402
from common.effects import CardEffects                          # noqa: E402
from common.pilot import Pilot                                  # noqa: E402
from common.scouting.provider import EngineCardStatProvider     # noqa: E402
from common.strategy import Strategy                            # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY   # noqa: E402
from common.strategy.planner import _prune_none                 # noqa: E402

REPO = Path(__file__).resolve().parents[2]
_AIR_BALLOON = 1174
_PETREL_STEP = [0]                                              # f15: option 0 = Play Team Rocket's Petrel


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _pilot(deck, **kw):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051)
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True, **kw)


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _tutor_menu_card_ids(pilot, obs, first_step):
    """Resolved card ids of the tutor menu after ``first_step``. Goes through ``pilot._seed_zones`` so
    the kill-switch decides exact-vs-prefix, exactly as the live verify does."""
    cur = obs["current"]
    yi = cur["yourIndex"]
    me, opp = cur["players"][yi], cur["players"][1 - yi]
    yd, yp, od, op_, oh = pilot._seed_zones(obs, me, opp)
    pilot._planning = True
    try:
        st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od, op_, oh, [],
                                manual_coin=True)
        st = cgapi.search_step(st.searchId, list(first_step))
        od_ = _prune_none(asdict(st.observation))
        sel = od_.get("select") or {}
        ids = [pilot._option_card_id(od_, sel, o) for o in (sel.get("option") or [])]
        cgapi.search_end()
        return ids
    finally:
        pilot._planning = False


@pytest.mark.req("REQ-LETHAL-SEED-0004")
def test_exact_seeding_exposes_the_deck_certain_air_balloon_that_prefix_hides():
    """The engine-level seeding gap: after Team Rocket's Petrel (tutor a Trainer), the deck-certain Air
    Balloon is offered under exact seeding and NOT under the id-sorted decklist prefix."""
    obs = _fixture("ml_petrel_balloon_retreat_lethal_f15")["obs"]
    assert obs.get("search_begin_input") and obs.get("own_prizes")   # fixture is seed-ready

    exact = _tutor_menu_card_ids(_pilot(_deck("mega_lucario")), obs, _PETREL_STEP)
    assert _AIR_BALLOON in exact                                     # reachable → the line is verifiable

    prefix = _tutor_menu_card_ids(_pilot(_deck("mega_lucario"), lethal_seed_exact=False),
                                  obs, _PETREL_STEP)
    assert _AIR_BALLOON not in prefix                                # the old prefix hid it


@pytest.mark.req("REQ-LETHAL-SEED-0004")
def test_applied_low_id_lethal_still_confirms_under_exact_seeding():
    """A shipped recover-energy lethal (f110, a low-id {W} Energy fetch that never depended on the
    prefix) must still confirm end-to-end under the exact-seeding fix — non-regression."""
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    obs = fx["obs"]
    assert obs.get("search_begin_input")
    pilot = _pilot(_deck("mega_starmie"))
    verdict = pilot._engine_confirms_win(obs, [fx["correct"]], max_cascade=40)
    assert verdict is True                                           # the engine still declares the win
