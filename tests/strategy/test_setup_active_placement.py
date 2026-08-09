"""Pregame Set-Up ACTIVE metadata (ADR-0079).

Issue #459 globally retires its sole shared scorer, `open-the-declared-starter`. Deck declarations
remain intact as scoped assets, but the runtime intentionally does not score them until a future
deck-local successor is specified. These tests guard that metadata boundary, not a selection outcome.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.cards import CardFunctions  # noqa: E402
from common.pilot import Pilot  # noqa: E402
from common.scouting.provider import CardStat, DictCardStatProvider  # noqa: E402
from common.strategy import Strategy  # noqa: E402
from common.strategy.context import _CARD, _SETUP_ACTIVE  # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "corrections"
AGENTS = REPO / "src" / "agents"

# dragapult_ex
DREEPY, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, BUDEW = 119, 112, 305, 140, 235
DRAKLOAK, DUDUNSPARCE = 120, 66      # the payoffs ADR-0081's Line clause must stay SILENT on
# mega_lucario
SOLROCK, RIOLU, MAKUHITA, LUNATONE = 676, 677, 673, 675
MEGA_LUCARIO_EX, HARIYAMA = 678, 674  # the declared Line payoff, and a non-Line payoff
# mega_starmie
CINDERACE, STARYU = 666, 1030
MEGA_STARMIE_EX = 1031
MEOWTH_EX = 1071   # in both dragapult_ex and mega_lucario


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _deck_strategy(agent: str):
    path = AGENTS / agent / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STRATEGY


def _authored_agents() -> list[str]:
    """Agents with a doctrine — a `STRATEGY.md` is the marker deck-genie has been run (ADR-0079
    amendment A). Pre-doctrine decks are exempt from the completeness invariant."""
    return sorted(d.name for d in AGENTS.iterdir()
                  if (d / "strategy.py").exists() and (d / "STRATEGY.md").exists())


def _exempt_agents() -> list[str]:
    """The pre-doctrine decks. Guarded on `deck.csv` so a stray directory under src/agents/ cannot
    break the exemption assertion for a reason unrelated to the invariant."""
    return sorted(d.name for d in AGENTS.iterdir()
                  if (d / "deck.csv").exists() and not (d / "STRATEGY.md").exists())


def _setup_active_obs(hand_ids, offer_ids=None):
    """A minimal SETUP_ACTIVE select. `offer_ids` exists because the hand-conditional opener
    (ADR-0081) turns on an EVOLUTION in hand, which is never a startable body and so never on offer."""
    hand_ids = list(hand_ids)
    idxs = range(len(hand_ids)) if offer_ids is None else [hand_ids.index(c) for c in offer_ids]
    opts = [{"type": _CARD, "area": 2, "index": i, "playerIndex": 0} for i in idxs]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_ACTIVE, "minCount": 1, "maxCount": 1, "option": opts}}


# ── The corrections this seam exists to fix ──────────────────────────────────────────────────────

def test_issue_459_keeps_starter_assets_but_global_runtime_does_not_score_them():
    """Starter orders stay complete metadata; the retired shared scorer must not fire for any deck."""
    offers = {"mega_lucario": [SOLROCK, RIOLU], "dragapult_ex": [BUDEW, DREEPY],
              "mega_starmie": [CINDERACE, STARYU]}
    assert all(_deck_strategy(agent).starter_priority for agent in offers)
    assert not any(h.id == "open-the-declared-starter" for h in GENERAL_STRATEGY.hypotheses)
    for agent, cards in offers.items():
        trace = _pilot(agent).explain(_setup_active_obs(cards))
        assert all(option.score == 0.0 and not option.fired for option in trace.options)

def test_f2_opens_the_utility_body_over_the_fragile_line_base():
    """dragapult f2, from its recorded observation: all three options returned 0.0 with NO rule
    firing, so the engine's option index opened the 70-HP Line base."""
    fx = json.loads((FIXTURES / "dp_open_utility_over_fragile_line_base_f2.json").read_text(encoding="utf-8"))
    chosen = _pilot("dragapult_ex").explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"f2: chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")




# ── REQ-OPEN-0002: the multi-prize demotion, re-expressed through the declaration ────────────────



@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_still_opens_meowth_when_it_is_the_only_basic():
    """Ranking last is not a ban: SETUP_ACTIVE is a forced single pick, so decide()'s take-fewer
    never trims a lone multi-prize body."""
    assert _pilot("mega_lucario").decide(_setup_active_obs([MEOWTH_EX])) == [0]


def test_a_declared_multiprize_starter_is_not_demoted():
    """The `_WINCON_ROLES` escape is now structural: a deck that MEANS to open a multi-prize body
    ranks it first, and nothing subtracts from that."""
    stats = DictCardStatProvider({MEOWTH_EX: CardStat(MEOWTH_EX, name="Meowth ex", hp=170, ex=True),
                                  RIOLU: CardStat(RIOLU, name="Riolu", hp=80)})
    pilot = Pilot(Strategy(starter_priority=[MEOWTH_EX, RIOLU]), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))
    assert pilot.decide(_setup_active_obs([MEOWTH_EX, RIOLU])) == [0]
    assert pilot.decide(_setup_active_obs([RIOLU, MEOWTH_EX])) == [1]


# ── The other decks' declared openers ────────────────────────────────────────────────────────────





def test_an_undeclared_deck_is_untouched():
    """Deck-keyed opt-in (ADR-0034): with no declaration the rule scores nothing at all, which is
    what makes the completeness invariant below load-bearing rather than decorative."""
    stats = DictCardStatProvider({RIOLU: CardStat(RIOLU, name="Riolu", hp=80),
                                  STARYU: CardStat(STARYU, name="Staryu", hp=70)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=CardFunctions({}))
    trace = pilot.explain(_setup_active_obs([RIOLU, STARYU]))
    assert all(o.score == 0.0 for o in trace.options)
    assert all(not o.fired for o in trace.options)




# ── ADR-0081: the Opener Marginal is `maxDamage(payoff) - maxDamage(body)` when a card in hand
# evolves from the offered body AND is the deck's declared `Line` payoff; otherwise ZERO.




def test_rank_one_holds_when_the_payoff_is_not_in_hand():
    """Case 2, the regression guard that gives case 1 its meaning. A general 2-turn readiness
    equation gets this WRONG and would need an underivable threshold (ADR-0081 decision 4)."""
    pilot = _pilot("mega_lucario")
    obs = _setup_active_obs([SOLROCK, RIOLU, MAKUHITA], offer_ids=[SOLROCK, RIOLU])
    assert pilot.decide(obs) == [0], "no payoff in hand — the declaration decides, untouched"
    flipped = _setup_active_obs([RIOLU, SOLROCK, MAKUHITA], offer_ids=[RIOLU, SOLROCK])
    assert pilot.decide(flipped) == [1], "order-independent"




def test_a_non_line_payoff_does_not_promote_the_draw_engine():
    """SILENCE 2/4: a draw engine is no Line payoff. Without the clause this is the deleted
    `dont-open-with-the-engine` failure back verbatim — the ranking subsumes it only while STATIC."""
    pilot = _pilot("dragapult_ex")
    obs = _setup_active_obs([DUNSPARCE, MUNKIDORI, DUDUNSPARCE], offer_ids=[DUNSPARCE, MUNKIDORI])
    assert pilot.decide(obs) == [1], "Munkidori (rank 2) still outranks Dunsparce (rank 3)"




# ── The derived pin tracks DECK COMPOSITION, not the card ────────────────────────────────────────

_OPENER, _BASE, _PAYOFF, _PRE = 9001, 9002, 9003, 9004
_RIVAL, _WINCON = 9005, 9006

_SYNTH_STATS = DictCardStatProvider({
    _OPENER: CardStat(_OPENER, name="Opener", hp=160, evolvesFrom="Pre", maxDamage=50),
    _BASE:   CardStat(_BASE, name="Base", hp=70, maxDamage=20),
    _PAYOFF: CardStat(_PAYOFF, name="Payoff", hp=210, evolvesFrom="Base", maxDamage=210),
    _PRE:    CardStat(_PRE, name="Pre", hp=90, maxDamage=30),
    _RIVAL:  CardStat(_RIVAL, name="Rival", hp=80, maxDamage=20),
    _WINCON: CardStat(_WINCON, name="Wincon", hp=300, evolvesFrom="Rival", maxDamage=250),
})


_UNSET = object()


def _synth_pilot(deck_ids, *, stats=_SYNTH_STATS, functions=_UNSET):
    """A two-body deck whose rank-1 is opener-tagged and evolves from "Pre". Whether "Pre" is IN the
    deck is the only thing that varies between the first two tests below."""
    from common.strategy.strategy import Line
    if functions is _UNSET:
        functions = CardFunctions({_OPENER: ["opener"]})
    strategy = Strategy(starter_priority=[_OPENER, _BASE],
                        lines=[Line(path=[_BASE, _PAYOFF], payoff=_PAYOFF)])
    return Pilot(strategy, deck=list(deck_ids), general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=functions)


def test_the_derived_pin_fires_when_the_deck_omits_the_evolution_route():
    """ADR-0081 decision 1: *is the Set-Up pick this body's only route into play?* — computed from
    the DECKLIST, not declared."""
    pilot = _synth_pilot([_OPENER] * 4 + [_BASE] * 4 + [_PAYOFF] * 4 + [1] * 48)
    obs = _setup_active_obs([_BASE, _OPENER, _PAYOFF], offer_ids=[_BASE, _OPENER])
    assert pilot.decide(obs) == [1], "route-restricted body is pinned at rank 1"




def test_the_pin_fails_CLOSED_when_it_cannot_tell():
    """A MISSING pin forfeits a card, a spurious one merely opens suboptimally. FUNCTIONS are
    withheld but STATS kept, or the Marginal would be 0 and the reorder skipped for another reason."""
    pilot = _synth_pilot([_OPENER] * 4 + [_BASE] * 4 + [_PAYOFF] * 4 + [_PRE] * 4 + [1] * 44,
                         functions=None)
    obs = _setup_active_obs([_BASE, _OPENER, _PAYOFF], offer_ids=[_BASE, _OPENER])
    assert pilot.decide(obs) == [1], "cannot evaluate the pin -> pin everything -> declaration stands"




def test_a_deck_with_no_declared_line_is_untouched():
    """The Marginal reads `Strategy.lines[].payoff`, so a deck that declares no Line gets no equation
    at all — fail-closed, and the reason the invariant below is owed."""
    from common.strategy.strategy import Line  # noqa: F401  (asserting the ABSENCE of one)
    strategy = Strategy(starter_priority=[_OPENER, _BASE])
    pilot = Pilot(strategy, deck=[_OPENER] * 4 + [_BASE] * 4 + [_PRE] * 4 + [1] * 48,
                  general_strategy=GENERAL_STRATEGY, stats=_SYNTH_STATS,
                  functions=CardFunctions({_OPENER: ["opener"]}))
    obs = _setup_active_obs([_BASE, _OPENER, _PAYOFF], offer_ids=[_BASE, _OPENER])
    assert pilot.decide(obs) == [1], "no Line declared -> no Marginal -> the declaration decides"


# ── The declaration invariant (the seam's SOLE guarantee) ────────────────────────────────────────

def test_every_authored_agent_declares_a_starter_priority():
    """ADR-0079 decision 5, presence half: a deck that declares nothing has NOTHING scoring its
    Set-Up Active pick and falls back to the engine's option-index order — the f2 / ml f1 bug."""
    for agent in _authored_agents():
        assert _deck_strategy(agent).starter_priority, (
            f"{agent}: authored deck (has STRATEGY.md) with no starter_priority — its Set-Up Active "
            f"pick would fall to the option-index tie-break")


def test_every_declaration_ranks_every_startable_body_in_the_deck():
    """ADR-0079 decision 5, completeness half: an unranked startable body could be offered while
    nothing scores. "Startable" is `Pilot._is_startable_body` — deliberately the runtime predicate."""
    for agent in _authored_agents():
        pilot = _pilot(agent)
        deck_ids = {int(line) for line in
                    (AGENTS / agent / "deck.csv").read_text(encoding="utf-8").split() if line.strip()}
        startable = {cid for cid in deck_ids if pilot._is_startable_body(cid)}
        # Fail CLOSED: `_is_startable_body` returns False for everything when stats fail to load,
        # and an empty `startable` satisfies the subset checks below vacuously.
        assert len(startable) >= 2, (
            f"{agent}: only {len(startable)} startable bodies resolved from {len(deck_ids)} deck ids — "
            f"card stats almost certainly failed to load, so this invariant would pass vacuously")
        declared = set(_deck_strategy(agent).starter_priority)
        assert not (startable - declared), (
            f"{agent}: startable bodies missing from starter_priority: {sorted(startable - declared)}")
        assert not (declared - startable), (
            f"{agent}: starter_priority ranks cards that cannot open: {sorted(declared - startable)}")


def test_every_authored_agent_declares_a_win_condition_line():
    """The Opener Marginal reads `Strategy.lines[].payoff`, so a deck with no Line silently stops
    being hand-conditional — a SILENT no-op rather than a wrong answer, hence the invariant."""
    for agent in _authored_agents():
        lines = _deck_strategy(agent).lines
        # The ROLE filter is the point: `_wincon_lines` drops `secondary_attacker` Lines (ADR-0048),
        # so asserting merely that SOME Line exists is the exact no-op this guards against.
        wincon = [ln for ln in lines if getattr(ln, "role", "win_condition") == "win_condition"]
        assert wincon, (
            f"{agent}: authored deck (has STRATEGY.md) declares no WIN-CONDITION Line — it may declare "
            f"other roles, but the Opener Marginal reads only win-condition payoffs, so its Set-Up "
            f"Active pick silently stops being hand-conditional")
        assert all(getattr(ln, "payoff", None) for ln in wincon), (
            f"{agent}: a declared win-condition Line has no payoff — the Marginal gates on it")


def test_the_exempt_agents_are_exactly_the_pre_doctrine_ones():
    """The exemption is asserted EXPLICITLY (ADR-0079 amendment A), so a new deck either gains a
    STRATEGY.md and a declaration or it fails here. Authoring both doctrines remains owed."""
    assert _exempt_agents() == ["hydrapple", "slowking"]
