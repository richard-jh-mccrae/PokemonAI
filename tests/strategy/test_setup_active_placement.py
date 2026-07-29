"""The pregame Set-Up ACTIVE pick: one rule reading one deck declaration (ADR-0075).

This file OWNS the `_SETUP_ACTIVE` seam. It replaces `test_setup_active_multiprize.py` (the
`dont-open-multiprize-active` demotion, REQ-OPEN-0002) and `test_budew_sacrificial_starter.py`'s
opener half, and absorbs the `f2` correction that sat `xfail(strict)` in
`test_evolve_valuation_corpus.py` aimed at the wrong code path.

Five scoring rules used to live at this seam — `open-the-accelerator` (+40),
`open-the-item-lock-starter` (+35), `dont-open-multiprize-active` (−15),
`dont-open-with-the-engine` (−12) and mega_lucario's card-id-gated `start-solrock-over-lunatone`
(+12). All are deleted. `Strategy.starter_priority` (an ordered, complete list of startable bodies)
plus the general `open-the-declared-starter` do the whole job.

**These are OUTCOME tests, never score tests.** What is asserted is which body ends up Active — the
behaviour the retired rungs bought — so the assertions survive a reweighting or another currency
change. The two seams (ADR-0075 / the /to-spec seam sketch):

  * behaviour  -> the Pilot's public decision entry point (`decide` / `explain`);
  * declaration-> each agent's loaded `Strategy`, for the completeness invariant, which has no
                  decision to ride on.

`board.top_starter_id` / `Context.card_is_top_starter` are deliberately NOT asserted: they are the
plumbing between the two, fully observable through the decision.

Card facts verified at source 2026-07-28 (`data/EN_Card_Data.csv`): Dreepy 70 HP / Petty Grudge {P}
10; Munkidori 110 HP / Mind Bend {P}+C 60; Solrock 110 HP / Cosmic Beam {F} 70; Lunatone 110 HP
(Lunar Cycle draw); Riolu 80 HP / Accelerating Stab {F} 30; Meowth ex 170 HP, 2 prizes; Budew 30 HP /
Itchy Pollen free, 10; Cinderace 160 HP, Explosiveness. Mulligan rule: `docs/rulebook.txt` L224.
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
from common.scouting.provider import CardStat  # noqa: E402
from common.strategy import Strategy  # noqa: E402
from common.strategy.context import _SETUP_ACTIVE  # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "corrections"
AGENTS = REPO / "src" / "agents"

# dragapult_ex
DREEPY, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, BUDEW = 119, 112, 305, 140, 235
# mega_lucario
SOLROCK, RIOLU, MAKUHITA, LUNATONE = 676, 677, 673, 675
# mega_starmie
CINDERACE, STARYU = 666, 1030
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
    """Agents with a doctrine — a `STRATEGY.md` is the marker deck-genie has been run (ADR-0075
    amendment A). Pre-doctrine decks are exempt from the completeness invariant; `_exempt_agents`
    asserts exactly which, so a new agent cannot silently opt out."""
    return sorted(d.name for d in AGENTS.iterdir()
                  if (d / "strategy.py").exists() and (d / "STRATEGY.md").exists())


def _exempt_agents() -> list[str]:
    """The pre-doctrine decks: a real agent directory (it has a deck) with no STRATEGY.md. Guarded on
    `deck.csv` for the same reason `_authored_agents` guards on `strategy.py` — without it a stray
    directory under src/agents/ (a __pycache__, a scratch dir) would break the exemption assertion
    for a reason that has nothing to do with the invariant."""
    return sorted(d.name for d in AGENTS.iterdir()
                  if (d / "deck.csv").exists() and not (d / "STRATEGY.md").exists())


def _setup_active_obs(hand_ids):
    """A minimal SETUP_ACTIVE select (minCount 1, maxCount 1) offering each hand card as the Active.
    Carried over verbatim from the retired `test_setup_active_multiprize.py` so the REQ-OPEN-0002
    assertions below are exercised through exactly the shape they were written against."""
    opts = [{"type": "Card", "area": 2, "index": i, "playerIndex": 0} for i in range(len(hand_ids))]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_ACTIVE, "minCount": 1, "maxCount": 1, "option": opts}}


# ── The corrections this seam exists to fix ──────────────────────────────────────────────────────

def test_f2_opens_the_utility_body_over_the_fragile_line_base():
    """dragapult f2 (86091728|0|decision|2), from its recorded observation.

    Was `xfail(strict)` in the EVOLVE corpus since 2026-07-15, labelled "exposure / opener", waiting
    on an equation that never runs on this path — ADR-0070 §4 re-ruled it out of scope and ADR-0075
    addressed it here. It was never mis-scored: all three options returned 0.0 with NO rule firing,
    so the engine's option index opened the 70-HP Line base. Munkidori (110 HP, Mind Bend 60) is
    rank 2 in the declaration; Dreepy is rank 5, deliberately below both ex's, because the Line base
    wants the BENCH."""
    fx = json.loads((FIXTURES / "dp_open_utility_over_fragile_line_base_f2.json").read_text(encoding="utf-8"))
    chosen = _pilot("dragapult_ex").explain(fx["obs"]).chosen
    assert chosen == fx["correct"], (
        f"f2: chose {chosen}, expected {fx['correct']} ({fx.get('correct_label')})")


def test_ml_f1_opens_the_attacker_over_the_draw_engine():
    """mega_lucario f1 (CRITICAL): Solrock (110 HP, Cosmic Beam 70 for one {F}) over Lunatone, the
    benched draw engine. The identical root cause as f2 — "both score 0, so the option-index
    tie-break opened Lunatone" — and until 2026-07-28 it was fixed by a rung gated on
    `card_id == SOLROCK`, the exact card-id reflex ADR-0075 removes. Order-independent."""
    pilot = _pilot("mega_lucario")
    assert pilot.decide(_setup_active_obs([LUNATONE, SOLROCK])) == [1]
    assert pilot.decide(_setup_active_obs([SOLROCK, LUNATONE])) == [0]


# ── REQ-OPEN-0002: the multi-prize demotion, re-expressed through the declaration ────────────────

@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_opens_the_plain_basic_over_meowth_ex():
    """REQ-OPEN-0002 (re-pointed from the deleted `dont-open-multiprize-active` to
    `open-the-declared-starter`): mega_lucario opens Riolu, not the 2-prize Meowth ex. Same outcome
    the −15 demotion bought — Meowth ex is simply ranked last — but now it also holds when the ex is
    the ONLY other option, and without a `_WINCON_ROLES` escape hatch."""
    pilot = _pilot("mega_lucario")
    assert pilot.decide(_setup_active_obs([MEOWTH_EX, RIOLU])) == [1], "should open Riolu, not Meowth ex"
    assert pilot.decide(_setup_active_obs([RIOLU, MEOWTH_EX])) == [0], "order-independent"


@pytest.mark.req("REQ-OPEN-0002")
def test_shipped_pilot_still_opens_meowth_when_it_is_the_only_basic():
    """REQ-OPEN-0002: ranking last is not a ban. SETUP_ACTIVE is a forced single pick (minCount 1),
    so a lone Meowth ex still takes the Active Spot — decide()'s take-fewer never trims it."""
    assert _pilot("mega_lucario").decide(_setup_active_obs([MEOWTH_EX])) == [0]


def test_a_declared_multiprize_starter_is_not_demoted():
    """The `_WINCON_ROLES` escape the old guard needed is now structural: a deck that MEANS to open a
    multi-prize body just ranks it first, and nothing subtracts from that. This is the case the
    grill's rejected 1..N rank scale got wrong (5 − 15 = −10, losing to an unranked Basic)."""
    stats = {MEOWTH_EX: CardStat(MEOWTH_EX, name="Meowth ex", hp=170, ex=True),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80)}
    pilot = Pilot(Strategy(starter_priority=[MEOWTH_EX, RIOLU]), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))
    assert pilot.decide(_setup_active_obs([MEOWTH_EX, RIOLU])) == [0]
    assert pilot.decide(_setup_active_obs([RIOLU, MEOWTH_EX])) == [1]


# ── The other decks' declared openers ────────────────────────────────────────────────────────────

def test_dragapult_opens_the_item_lock_starter_over_everything():
    """Budew is rank 1: a free Itchy Pollen taxes an Item-heavy setup while our line assembles. The
    outcome the retired `open-the-item-lock-starter` (+35) bought, now ordered against the whole
    field rather than against whatever else happened to score."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, MUNKIDORI, BUDEW])) == [2]
    assert pilot.decide(_setup_active_obs([BUDEW, MEOWTH_EX])) == [0]


def test_dragapult_ranks_the_line_base_below_the_bodies_it_can_spare():
    """The user ruling this order encodes (2026-07-28): Dreepy is 5th, BELOW a 2-prize Fezandipiti ex
    and a Dunsparce. Not a fragility read — it is a PLACEMENT read. Dreepy is the win-condition Line
    base and belongs on the Bench evolving toward Dragapult ex; an Active Dreepy is a line that is
    not being built. A naive fragility+prize-liability heuristic ranks it the other way round."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, FEZANDIPITI_EX])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, MEOWTH_EX])) == [0], "but still above Meowth ex"


def test_mega_starmie_opens_cinderace_over_the_wincon_base():
    """Cinderace (160 HP, Explosiveness + Turbo Flare) opens; Staryu is the Line base and wants the
    Bench. The outcome `open-cinderace` → `open-the-accelerator` (+40) bought — the weight band
    `docs/weights.md` cites as its core-doctrine exemplar, which is why the successor seeds at 40."""
    pilot = _pilot("mega_starmie")
    assert pilot.decide(_setup_active_obs([STARYU, CINDERACE])) == [1]
    assert pilot.decide(_setup_active_obs([CINDERACE, STARYU])) == [0]


def test_an_undeclared_deck_is_untouched():
    """Deck-keyed opt-in (ADR-0034): with no declaration the rule is silent and scores nothing, so a
    pre-doctrine agent behaves exactly as it would with the rule absent. This is what makes the
    completeness invariant below load-bearing rather than decorative."""
    stats = {RIOLU: CardStat(RIOLU, name="Riolu", hp=80), STARYU: CardStat(STARYU, name="Staryu", hp=70)}
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=CardFunctions({}))
    trace = pilot.explain(_setup_active_obs([RIOLU, STARYU]))
    assert all(o.score == 0.0 for o in trace.options)
    assert all(not o.fired for o in trace.options)


def test_the_highest_ranked_body_PRESENT_wins_not_merely_rank_one():
    """`board.top_starter_id` resolves against what is actually on offer, so the whole ordering
    collapses into one boolean losslessly: with Budew absent, dragapult's rank-2 Munkidori leads;
    with Munkidori also absent, rank-3 Dunsparce does. This is the property that makes a boolean
    equivalent to a rank scale under a COMPLETE list (ADR-0075 decision 5)."""
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(_setup_active_obs([DREEPY, MUNKIDORI])) == [1]
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE, MUNKIDORI])) == [2]
    assert pilot.decide(_setup_active_obs([DREEPY, DUNSPARCE])) == [1]


# ── The declaration invariant (the seam's SOLE guarantee) ────────────────────────────────────────

def test_every_authored_agent_declares_a_starter_priority():
    """ADR-0075 decision 5, the presence half. With the five old rungs deleted, a deck that declares
    nothing has NOTHING scoring its Set-Up Active pick and falls back to the engine's option-index
    order — which is precisely the f2 / ml f1 bug. Non-negotiable for an authored agent."""
    for agent in _authored_agents():
        assert _deck_strategy(agent).starter_priority, (
            f"{agent}: authored deck (has STRATEGY.md) with no starter_priority — its Set-Up Active "
            f"pick would fall to the option-index tie-break")


def test_every_declaration_ranks_every_startable_body_in_the_deck():
    """ADR-0075 decision 5, the completeness half — the invariant that makes the single-winner read
    EXACT rather than merely usually right. If a startable body were unranked it could be offered
    while nothing scores, re-creating the tie-break bug; and a partial list would let a low-ranked
    body inherit the full weight of a rank-1 opener.

    "Startable" is `Pilot._is_startable_body` — a Basic, or an `opener`-tagged card (Explosiveness).
    Deliberately the SAME predicate the runtime uses, so the test cannot drift from what the engine
    can actually offer."""
    for agent in _authored_agents():
        pilot = _pilot(agent)
        deck_ids = {int(line) for line in
                    (AGENTS / agent / "deck.csv").read_text(encoding="utf-8").split() if line.strip()}
        startable = {cid for cid in deck_ids if pilot._is_startable_body(cid)}
        # Fail CLOSED. `_is_startable_body` returns False for every card when stats fail to load, and
        # an empty `startable` would satisfy the subset checks below vacuously — the invariant would
        # go green while measuring nothing. Every real deck has at least two startable bodies.
        assert len(startable) >= 2, (
            f"{agent}: only {len(startable)} startable bodies resolved from {len(deck_ids)} deck ids — "
            f"card stats almost certainly failed to load, so this invariant would pass vacuously")
        declared = set(_deck_strategy(agent).starter_priority)
        assert not (startable - declared), (
            f"{agent}: startable bodies missing from starter_priority: {sorted(startable - declared)}")
        assert not (declared - startable), (
            f"{agent}: starter_priority ranks cards that cannot open: {sorted(declared - startable)}")


def test_the_exempt_agents_are_exactly_the_pre_doctrine_ones():
    """The exemption is asserted EXPLICITLY (ADR-0075 amendment A), so adding an agent cannot
    silently opt out of the invariant above — a new deck either gains a STRATEGY.md and a declaration
    or it fails here. `grimmsnarl_ex` (strategy.py but no doctrine) and `slowking` (a decklist only)
    are the two known pre-doctrine decks; both are /deck-genie's job, and /deck-align's
    "≥2 startable bodies, no starter_priority" check is what surfaces them."""
    assert _exempt_agents() == ["grimmsnarl_ex", "slowking"]
