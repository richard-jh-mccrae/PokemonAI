"""M3 verdict-agreement gate (ADR-0050): the planner's engine drivers must reach the SAME
verdict on the native engine and on the cgpy twin, on every seeded correction fixture.

`_engine_confirms_win` is the sound Solver hook (a phantom win loses the game), so the
agreement rule is strict where it matters: whenever cgpy reaches a verdict it must equal
native's; cgpy may return None (undetermined) where native decides — None never lies — but
the suite also pins the known-decidable fixtures so the twin can't silently degrade to
all-None. Imports the committed native lib (skips cleanly without it); the cgpy side runs
through `cgpy.alias` in the same process — the planner's per-call ``from cg import api``
resolves whichever engine the alias maps at call time.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("cg")

from common.cards import CardFunctions                           # noqa: E402
from common.effects import CardEffects                           # noqa: E402
from common.pilot import Pilot                                   # noqa: E402
from common.scouting.provider import EngineCardStatProvider      # noqa: E402
from common.strategy import Strategy                             # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY    # noqa: E402
from lethal_helpers import engine_confirms                       # noqa: E402

from cgpy import alias                                           # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# The seeded fixtures (search_begin_input + own_prizes backfilled — the recorded
# planner-call corpus) whose cascade is DRAW-FREE, so the verdict is prediction-invariant
# and the two engines must agree. f15 is deliberately absent: its recorded step is the
# retired dead-hand framing (Lillie's = shuffle-hand-in, draw 6), whose outcome hinges on
# WHICH cards the fork deals — order-dependent by the planner's own doctrine (its native
# verdict varies with the process's prior searches). Its Petrel win line is gated
# deterministically in test_lethal_cgpy.py instead.
#
# ml f24 joins that exclusion (#178, re-ruled 2026-07-27). It was listed here on the
# ASSUMPTION that it is draw-free; measured, it is the only member that is not — its
# cascade shuffles three cards from hand back in and then takes ELEVEN draws off the
# shuffled predicted deck, where f26/f48 only tutor (a search picks by identity, so the
# order decides nothing) and f110 only takes its own prizes
# (`test_every_seeded_cascade_is_really_draw_free` now measures this rather than assuming
# it, and pins f24 as the counter-example so the exclusion cannot rot). Its native verdict
# is therefore a SAMPLE: cgpy is deterministic here (`SeededRng(0)`) and answers False
# every time, while native answers False on most streams and True on some — which is the
# `cgpy verdict False contradicts native True` failure CI hit on PR #179. Nothing about
# the twin's fidelity is in question, so there is nothing for this gate to prove on it.
EXCLUDED_FIXTURES = {
    "ml_lethal_retreat_boost_to_ko_f24": "cascade draws off the shuffled deck (#178)",
}

SEEDED_FIXTURES = [
    ("ms_lethal_recover_energy_to_win_f110", "mega_starmie"),
    ("ml_lethal_recover_energy_retreat_ko_f26", "mega_lucario"),
    ("ml_lethal_recover_energy_via_gong_f48", "mega_lucario"),
]


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _pilot(deck):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider (ADR-0051); it lazily builds off whichever engine
    # the cgpy alias maps at call time, so native/twin parity is preserved.
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


def _both_verdicts(name, agent):
    fx = _fixture(name)
    native = engine_confirms(fx, _pilot(_deck(agent)))
    alias.install()
    try:
        py = engine_confirms(fx, _pilot(_deck(agent)))
    finally:
        alias.uninstall()
    return native, py


@pytest.mark.req("REQ-CGPY-M3-0012")
@pytest.mark.parametrize("name,agent", SEEDED_FIXTURES, ids=lambda v: v)
def test_engine_confirms_win_verdicts_agree(name, agent):
    native, py = _both_verdicts(name, agent)
    assert native is not None, f"{name}: native verdict unavailable — fixture seed broken?"
    assert py == native or py is None, (
        f"{name}: cgpy verdict {py!r} contradicts native {native!r}")


@pytest.mark.req("REQ-CGPY-M3-0012")
def test_agreement_is_not_vacuous():
    """The twin must actually decide the decidable: the shipped recover-energy win (f110)
    confirms True on BOTH engines — the whole fetch->attach->retreat->promote->attack->win
    cascade drives through cgpy to the same verdict."""
    native, py = _both_verdicts("ms_lethal_recover_energy_to_win_f110", "mega_starmie")
    assert native is True and py is True


def _cascade_reveals(name, agent):
    """Drive ``name``'s native cascade and return the engine-RNG reveals it consumed.

    The membership criterion for `SEEDED_FIXTURES`, measured instead of assumed: a cascade that
    takes a card POSITIONALLY out of a shuffled hidden zone has a verdict that is a sample of that
    shuffle, not a fact about the board (`_seed_zones` hands `search_begin` a predicted MULTISET;
    the engine shuffles it, and the native engine is unseedable). Counts MY-side ``DRAW``, a
    ``DECK``→``LOOKING`` peek or ``DECK``→``DISCARD`` mill, and any ``COIN``.

    Three kinds of hidden-zone traffic are deliberately NOT counted, each because it cannot move
    the VERDICT (a narrower question than `_simulate_line`'s ``stream`` bit, which also has to
    protect an end-of-turn BOARD):

      * bare ``SHUFFLE`` — `search_begin` shuffles the seeded zones on every fixture, and a
        shuffle nobody then looks at changes nothing;
      * ``DECK``→``HAND`` / ``DECK``→field — a **search**: the deck is revealed and we pick by
        identity, so the order decides nothing (this is all the hidden-zone traffic f26 and f48
        have, on their tutor lines);
      * ``PRIZE``→``HAND`` — the win's own prize take. `_engine_confirms_win` already documents
        that "the ``result`` verdict is invariant to WHICH prize is taken" (ADR-0050); it is the
        only such traffic on f110, the fixture that anchors `test_agreement_is_not_vacuous`."""
    from cg import api as cgapi

    fx = _fixture(name)
    yi = ((fx["obs"].get("current") or {}).get("yourIndex")) or 0
    positional = {(int(cgapi.AreaType.DECK), int(cgapi.AreaType.LOOKING)),
                  (int(cgapi.AreaType.DECK), int(cgapi.AreaType.DISCARD))}
    seen = set()

    def _collect(st):
        for lg in (getattr(st.observation, "logs", None) or ()):
            t = getattr(lg, "type", None)
            if t == cgapi.LogType.COIN:
                seen.add("COIN")
            elif getattr(lg, "playerIndex", None) != yi:
                continue
            elif t == cgapi.LogType.DRAW:
                seen.add("DRAW")
            elif t == cgapi.LogType.MOVE_CARD and (int(getattr(lg, "fromArea", 0) or 0),
                                                   int(getattr(lg, "toArea", 0) or 0)) in positional:
                seen.add("DECK_TOP_REVEAL")
        return st

    begin, step = cgapi.search_begin, cgapi.search_step
    cgapi.search_begin = lambda *a, **kw: _collect(begin(*a, **kw))
    cgapi.search_step = lambda *a, **kw: _collect(step(*a, **kw))
    try:
        engine_confirms(fx, _pilot(_deck(agent)))
    finally:
        cgapi.search_begin, cgapi.search_step = begin, step
    return seen


@pytest.mark.req("REQ-CGPY-M3-0012")
@pytest.mark.parametrize("name,agent", SEEDED_FIXTURES, ids=lambda v: v)
def test_every_seeded_cascade_is_really_draw_free(name, agent):
    """The gate's admission rule, enforced in code rather than asserted in a comment (#178).

    A fixture belongs in `SEEDED_FIXTURES` only if its verdict is prediction-invariant, and the
    reason it would fail to be is that the cascade takes a card off a shuffled hidden zone. That
    was written down as a property of this list and was FALSE for one of its members for as long
    as the list existed, which is what made the gate flaky. Measure it."""
    assert not _cascade_reveals(name, agent), (
        f"{name}: this cascade consumes engine randomness, so its verdict is a sample of the "
        f"shuffle — it cannot gate native/cgpy agreement. Exclude it like ml f24 and f15.")


@pytest.mark.req("REQ-CGPY-M3-0012")
def test_the_excluded_fixture_really_does_draw():
    """The negative control that keeps the exclusion honest: ml f24 is out of the gate because its
    cascade draws, so that had better still be true. If this ever goes green the exclusion has
    become a stale deferral and f24 belongs back in `SEEDED_FIXTURES`."""
    assert "ml_lethal_retreat_boost_to_ko_f24" in EXCLUDED_FIXTURES
    assert _cascade_reveals("ml_lethal_retreat_boost_to_ko_f24", "mega_lucario") >= {"DRAW"}


@pytest.mark.req("REQ-CGPY-M3-0013")
def test_simulate_line_runs_on_both_engines():
    """The heuristic ranker (`_simulate_line`) is order-DEPENDENT by design (coins
    auto-resolve, draws differ per shuffle), so only availability is asserted: where the
    native path returns an end-board value, the cgpy path must return one too."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")     # a MAIN-select seeded fixture
    obs, first = fx["obs"], fx["correct"]
    native = _pilot(_deck("mega_lucario"))._simulate_line(obs, list(first))
    alias.install()
    try:
        py = _pilot(_deck("mega_lucario"))._simulate_line(obs, list(first))
    finally:
        alias.uninstall()
    assert (native is None) == (py is None)
    if native is not None:
        assert py is not None
