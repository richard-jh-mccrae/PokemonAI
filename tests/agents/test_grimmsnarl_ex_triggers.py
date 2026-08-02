"""`grimmsnarl_ex` — the first agent deck that can actually reach the Rare Candy KO composer.

`enabler_item_composer` (BUILD 1, `planner._rare_candy_ko_candidate`) is **armed ON in the deployment
PROFILE**, and its own docstring recorded it as INERT: *"NONE of the 3 current agent decks run Rare
Candy or a Basic→Stage-1→Stage-2 line — this branch is inert for them. It is forward-looking
generality, exercised only by tests today."* That claim expired when `grimmsnarl_ex` shipped, and
Issue #288 noticed only because the same card pair forces `common.playability`'s Rare Candy escape:

  * 1× **Rare Candy** (id 1079) — *"Choose 1 of your Basic Pokémon in play. If you have a Stage 2 card
    in your hand that evolves from that Pokémon, put that card onto the Basic Pokémon to evolve it,
    skipping the Stage 1"*;
  * the full **Marnie's Impidimp** (646, Basic) → **Marnie's Morgrem** (647) → **Marnie's Grimmsnarl
    ex** (648, `stage2`) line, whose attack 937 deals **180 for {D}{D}**.

All verified at `data/EN_Card_Data.csv` / the shipped Stat Provider, not recalled.

So an armed planner branch became live on a shipped deck with nothing exercising it there — the whole
of its coverage was a synthetic four-card pool. These tests close that: the composer is driven
through the **real engine-backed Pilot**, on the real line, and every refusal clause is checked on the
same board so a silent stand-down cannot pass for correctness.

**Measured 2026-08-02: the branch is correct on this deck.** It was not obviously so — the first
probe read `None` on a board that should compose, and the cause was the FIXTURE, not the code: attack
937 costs {D}{D}, the Impidimp carried one, and the hand held no attachable Energy, so the Attach
Budget offered nothing and the line could not pay. That near-miss is why `test_the_composer_needs_a
_payable_attack` exists — a composer that stands down for want of Energy and one that stands down
because it is broken look identical from the outside.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from common.pilot import Board
from pilot_helpers import PLAY, make_select, opt, poke, state

REPO = Path(__file__).resolve().parents[2]

IMPIDIMP, MORGREM, GRIMMSNARL = 646, 647, 648   # the Basic -> Stage 1 -> Stage 2 line
RARE_CANDY, DARK = 1079, 7                      # the Item, and a Basic {D} Energy
GRIMMSNARL_ATTACK = 937                         # 180 damage for {D}{D}
OPP = 320                                       # an opposing body, HP set per case


def _pilot():
    """The agent's real engine-backed Pilot — the point of this file. `_build_pilot` resolves the one
    deployment PROFILE (ADR-0055), so `enabler_item_composer` is whatever actually ships."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("grimmsnarl_ex")[0]


def _compose(pilot, *, turn=4, opp_hp=170, appear_this_turn=False, stage2_in_hand=True,
             hand=(RARE_CANDY, DARK), attached=1):
    """Drive `_rare_candy_ko_candidate` on a board this deck can really be in: Marnie's Impidimp
    Active carrying ``attached`` {D}, Rare Candy on the menu, the Stage 2 in hand.

    ``hand`` is the OBS hand (what the Attach Budget can actually pay from) while the Stage 2 rides
    `Board.hand_ids` — the split the composer itself reads, since Rare Candy is not a tutor and needs
    the Stage 2 already held."""
    body = poke(IMPIDIMP, energy=attached, hp=70)
    body["energies"] = [DARK] * attached
    if appear_this_turn:
        body["appearThisTurn"] = True
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=body, opp_active=poke(OPP, hp=opp_hp), turn=turn,
                                    hand=list(hand)))
    board = Board(turn=turn, hand_ids=frozenset({GRIMMSNARL} if stage2_in_hand else ()),
                  basic_energy_in_deck=True, no_supporter_in_hand=True)
    # `_board` first, exactly as production does: the Attach Budget lives on the StateModel, and a
    # planner internal called cold measures a fail-closed zero (ADR-0075).
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    return pilot._rare_candy_ko_candidate(obs, obs["select"], board, obs["select"]["option"][0],
                                          {"id": OPP, "hp": opp_hp}, {}, True)


@pytest.mark.req("REQ-GRIMM-0001")
def test_the_deck_really_can_reach_the_rare_candy_branch():
    """The premise, asserted rather than assumed — this is what went stale last time. All four facts
    are read off the shipped deck and Stat Provider, so adding or dropping any of them reddens here
    instead of silently re-inerting the branch."""
    pilot = _pilot()
    assert pilot.enabler_item_composer is True, "the composer is not armed — these tests prove nothing"
    assert RARE_CANDY in set(pilot.deck), "grimmsnarl_ex no longer runs Rare Candy"
    top = pilot.stats.get(GRIMMSNARL)
    assert top.stage2 and top.evolvesFrom == "Marnie's Morgrem"
    assert pilot.stats.get(MORGREM).evolvesFrom == "Marnie's Impidimp"
    assert pilot.stats.get(IMPIDIMP).evolvesFrom is None, "the root must be a Basic"
    assert pilot._stage2_roots_at(top, "Marnie's Impidimp") is True


@pytest.mark.req("REQ-GRIMM-0001")
def test_the_composer_finds_the_stage_two_skip_on_the_real_line():
    """Impidimp Active with one {D}, a second {D} in hand, Rare Candy on the menu, Grimmsnarl ex held:
    play the Candy, skip Morgrem, attach, and Mean Kick's 180 knocks out a 170-HP body. The composer
    returns `(prizes, active_survives, p)` — 320 HP of Grimmsnarl ex comfortably survives the reply,
    and the line is certain (p = 1.0) because every step is already in hand."""
    got = _compose(_pilot())
    assert got is not None, "the armed composer is inert on the one deck that can reach it"
    prizes, survives, p = got
    assert prizes >= 1 and survives is True and p == pytest.approx(1.0)


@pytest.mark.req("REQ-GRIMM-0001")
def test_the_composer_needs_a_payable_attack():
    """The near-miss that made this file worth writing. Attack 937 costs **{D}{D}** (verified), so a
    one-{D} Impidimp with no Energy in hand cannot pay for it however good the KO looks — the Attach
    Budget offers nothing and the line prices out. Give it either route and it composes again.

    Pinned because a composer standing down for want of Energy and one standing down because it is
    BROKEN are indistinguishable from the outside — which is exactly how the first probe of this
    branch was misread."""
    pilot = _pilot()
    assert _compose(pilot, hand=(RARE_CANDY,), attached=1) is None      # nothing to attach
    assert _compose(pilot, hand=(RARE_CANDY,), attached=2) is not None  # already powered
    assert _compose(pilot, hand=(RARE_CANDY, DARK), attached=1) is not None   # pays from hand


@pytest.mark.req("REQ-GRIMM-0001")
@pytest.mark.parametrize("case,kwargs", [
    ("no KO is reachable", {"opp_hp": 400}),
    ("Rare Candy is illegal on your first turn", {"turn": 1}),
    ("the Basic was put into play this turn", {"appear_this_turn": True}),
    ("the Stage 2 is not in hand — Rare Candy is no tutor", {"stage2_in_hand": False}),
])
def test_every_refusal_clause_holds_on_the_real_deck(case, kwargs):
    """Each clause of the card's own text and the composer's soundness, checked on the board that
    otherwise composes — so a stand-down is attributable to the clause under test rather than to the
    fixture failing to set the line up at all."""
    assert _compose(_pilot(), **kwargs) is None, f"composed anyway when {case}"
