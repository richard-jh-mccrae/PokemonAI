"""The pregame Set-Up ACTIVE pick: one rule reading one deck declaration (ADR-0079).

This file OWNS the `_SETUP_ACTIVE` seam. Five scoring rules used to live here; all are deleted, and
`Strategy.starter_priority` (an ordered, COMPLETE list of startable bodies) plus the general
`open-the-declared-starter` do the whole job.

**These are OUTCOME tests, never score tests** — what is asserted is which body ends up Active,
through `decide`/`explain`, plus the completeness invariant read off each agent's loaded `Strategy`.
`board.top_starter_id` / `Context.card_is_top_starter` are deliberately NOT asserted: they are the
plumbing between the two, fully observable through the decision.

Card facts verified at source (`data/EN_Card_Data.csv`); mulligan rule at `docs/rulebook.txt` L224.
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

def test_f2_opens_the_utility_body_over_the_fragile_line_base():
    """dragapult f2, from its recorded observation: all three options returned 0.0 with NO rule
    firing, so the engine's option index opened the 70-HP Line base."""
    fx = json.loads((FIXTURES / "dp_open_utility_over_fragile_line_base_f2.json").read_text(encoding="utf-8"))
    chosen = _pilot("dragapult_ex").explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"f2: chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


def test_ml_f1_opens_the_attacker_over_the_draw_engine():
    """mega_lucario f1 (CRITICAL): Solrock over Lunatone, the benched draw engine. Same root cause as
    f2, and it used to be fixed by a rung gated on `card_id == SOLROCK` (ADR-0079 removes that)."""
    pilot = _pilot("mega_lucario")
    assert pilot.decide(_setup_active_obs([LUNATONE, SOLROCK])) == [1]
    assert pilot.decide(_setup_active_obs([SOLROCK, LUNATONE])) == [0]


# ── REQ-OPEN-0002: the multi-prize demotion, re-expressed through the declaration ────────────────

@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_opens_the_plain_basic_over_meowth_ex():
    """Same outcome the deleted −15 demotion bought — Meowth ex is simply ranked last — but it now
    holds when the ex is the ONLY other option, and without a `_WINCON_ROLES` escape hatch."""
    pilot = _pilot("mega_lucario")
    assert pilot.decide(_setup_active_obs([MEOWTH_EX, RIOLU])) == [1], "should open Riolu, not Meowth ex"
    assert pilot.decide(_setup_active_obs([RIOLU, MEOWTH_EX])) == [0], "order-independent"


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

def test_dragapult_opens_the_item_lock_starter_over_everything():
    """Budew is rank 1 — the outcome the retired `open-the-item-lock-starter` bought, now ordered
    against the whole field rather than against whatever else happened to score."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, MUNKIDORI, BUDEW])) == [2]
    assert pilot.decide(_setup_active_obs([BUDEW, MEOWTH_EX])) == [0]


def test_dragapult_ranks_the_line_base_below_the_bodies_it_can_spare():
    """A PLACEMENT read, not a fragility one: the Line base belongs on the Bench evolving, so an
    Active Dreepy is a line that is not being built. A fragility heuristic ranks it the other way."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, FEZANDIPITI_EX])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, MEOWTH_EX])) == [0], "but still above Meowth ex"


def test_mega_starmie_opens_cinderace_over_the_wincon_base():
    """Cinderace opens; Staryu is the Line base and wants the Bench — the outcome the retired
    `open-the-accelerator` bought."""
    pilot = _pilot("mega_starmie")
    assert pilot.decide(_setup_active_obs([STARYU, CINDERACE])) == [1]
    assert pilot.decide(_setup_active_obs([CINDERACE, STARYU])) == [0]


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


def test_the_highest_ranked_body_PRESENT_wins_not_merely_rank_one():
    """`board.top_starter_id` resolves against what is on OFFER, which is what makes a boolean
    equivalent to a rank scale under a COMPLETE list (ADR-0079 decision 5)."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, MUNKIDORI])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE, MUNKIDORI])) == [2]
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE])) == [1]


# ── ADR-0081: the Opener Marginal is `maxDamage(payoff) - maxDamage(body)` when a card in hand
# evolves from the offered body AND is the deck's declared `Line` payoff; otherwise ZERO.


def test_the_line_base_beats_rank_one_when_its_wincon_payoff_is_in_hand():
    """ADR-0081 case 1: holding the Mega flips a declared rank-1. Read with the case-2 test below —
    the SAME two bodies on offer, only the hand differs, so this is an inversion not a tie-break."""
    pilot = _pilot("mega_lucario")
    obs = _setup_active_obs([SOLROCK, RIOLU, MEGA_LUCARIO_EX], offer_ids=[SOLROCK, RIOLU])
    assert pilot.decide(obs) == [1], "should open Riolu — the Mega in hand makes it a 2-turn 130"
    flipped = _setup_active_obs([RIOLU, SOLROCK, MEGA_LUCARIO_EX], offer_ids=[RIOLU, SOLROCK])
    assert pilot.decide(flipped) == [0], "order-independent"


def test_rank_one_holds_when_the_payoff_is_not_in_hand():
    """Case 2, the regression guard that gives case 1 its meaning. A general 2-turn readiness
    equation gets this WRONG and would need an underivable threshold (ADR-0081 decision 4)."""
    pilot = _pilot("mega_lucario")
    obs = _setup_active_obs([SOLROCK, RIOLU, MAKUHITA], offer_ids=[SOLROCK, RIOLU])
    assert pilot.decide(obs) == [0], "no payoff in hand — the declaration decides, untouched"
    flipped = _setup_active_obs([RIOLU, SOLROCK, MAKUHITA], offer_ids=[RIOLU, SOLROCK])
    assert pilot.decide(flipped) == [1], "order-independent"


def test_a_mid_line_payoff_does_not_promote_the_line_base():
    """SILENCE 1/4: a MID-line card is a stepping stone, not the declared payoff. Without the Line
    clause this frame promotes Dreepy above Dunsparce and overturns ADR-0079 amendment B."""
    pilot = _pilot("dragapult_ex")
    obs = _setup_active_obs([DREEPY, DUNSPARCE, DRAKLOAK], offer_ids=[DREEPY, DUNSPARCE])
    assert pilot.decide(obs) == [1], "Dunsparce (rank 3) still outranks Dreepy (rank 5)"


def test_a_non_line_payoff_does_not_promote_the_draw_engine():
    """SILENCE 2/4: a draw engine is no Line payoff. Without the clause this is the deleted
    `dont-open-with-the-engine` failure back verbatim — the ranking subsumes it only while STATIC."""
    pilot = _pilot("dragapult_ex")
    obs = _setup_active_obs([DUNSPARCE, MUNKIDORI, DUDUNSPARCE], offer_ids=[DUNSPARCE, MUNKIDORI])
    assert pilot.decide(obs) == [1], "Munkidori (rank 2) still outranks Dunsparce (rank 3)"


def test_a_secondary_attacker_line_payoff_does_not_promote_its_base():
    """SILENCE 3/4: Hariyama out-damages the Mega but its Line is `role="secondary_attacker"`. The
    gate is `_wincon_lines`, so being the declared WIN CONDITION is what counts, not damage."""
    pilot = _pilot("mega_lucario")
    obs = _setup_active_obs([SOLROCK, MAKUHITA, HARIYAMA], offer_ids=[SOLROCK, MAKUHITA])
    assert pilot.decide(obs) == [0], "Solrock's rank 1 holds — Hariyama is not the Line payoff"


def test_the_setup_only_body_still_opens_against_a_large_in_line_payoff():
    """SILENCE 4/4, the one the derived PIN exists for: Staryu's Marginal is a genuine +190, but the
    Set-Up pick is Cinderace's only route into play (no Raboot in the deck) so skipping it forfeits it."""
    pilot = _pilot("mega_starmie")
    obs = _setup_active_obs([STARYU, CINDERACE, MEGA_STARMIE_EX], offer_ids=[STARYU, CINDERACE])
    assert pilot.decide(obs) == [1], "Cinderace opens — a +190 Marginal must not cost us the card"


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


def test_the_derived_pin_LIFTS_when_the_deck_runs_the_evolution_route():
    """Why the pin is DERIVED: add "Pre" to the deck and it lifts by itself. A declared pin would go
    stale here and silently keep protecting a body that no longer needs it."""
    pilot = _synth_pilot([_OPENER] * 4 + [_BASE] * 4 + [_PAYOFF] * 4 + [_PRE] * 4 + [1] * 44)
    obs = _setup_active_obs([_BASE, _OPENER, _PAYOFF], offer_ids=[_BASE, _OPENER])
    assert pilot.decide(obs) == [0], "pin lifted — the payoff in hand promotes the Line base"


def test_the_pin_fails_CLOSED_when_it_cannot_tell():
    """A MISSING pin forfeits a card, a spurious one merely opens suboptimally. FUNCTIONS are
    withheld but STATS kept, or the Marginal would be 0 and the reorder skipped for another reason."""
    pilot = _synth_pilot([_OPENER] * 4 + [_BASE] * 4 + [_PAYOFF] * 4 + [_PRE] * 4 + [1] * 44,
                         functions=None)
    obs = _setup_active_obs([_BASE, _OPENER, _PAYOFF], offer_ids=[_BASE, _OPENER])
    assert pilot.decide(obs) == [1], "cannot evaluate the pin -> pin everything -> declaration stands"


def test_a_ROLE_tagged_body_that_is_no_line_payoff_does_not_promote_its_base():
    """The gate is the declared **Line payoff**, never the win-condition **Role** set. The two sets
    COINCIDE on every authored deck, so collapsing them reddens nothing but this test."""
    from common.strategy.strategy import Line
    strategy = Strategy(starter_priority=[_RIVAL, _BASE],
                        lines=[Line(path=[_RIVAL, _WINCON], payoff=_WINCON)],
                        roles={_PAYOFF: ["primary_attacker"]})
    pilot = Pilot(strategy, deck=[_RIVAL] * 4 + [_BASE] * 4 + [_PAYOFF] * 4 + [_WINCON] * 4 + [1] * 44,
                  general_strategy=GENERAL_STRATEGY, stats=_SYNTH_STATS, functions=CardFunctions({}))
    obs = _setup_active_obs([_BASE, _RIVAL, _PAYOFF], offer_ids=[_BASE, _RIVAL])
    assert pilot.decide(obs) == [1], (
        "a `primary_attacker`-Roled body that is on no declared Line must NOT act as an opener "
        "payoff — the declared rank 1 holds")


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
