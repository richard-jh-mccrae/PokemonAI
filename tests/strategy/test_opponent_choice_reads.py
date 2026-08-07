"""ADR-0044 — the deferred opponent-choice residue as narrow closed-form reads.

Two snipe-target reads that let a match-scale objective override the prize-blind threat rank,
each behind its own kill-switch, γ-gated, default OFF:

- **Prize-Redundant Target** (`snipe_prize_redundant`, 83667237-107): don't spend snipe chip on an
  off-Prize-Path body whose prizes I don't need — "one Mega + a small, deny the second Mega".
- **Forced-Promotion Read** (`forced_promotion`, 83661649-45): when the opponent's Active is dead a
  promotion is forced; pre-chip the ready wincon they will bring up, not the energized bench-sitter.

Both flipped **DEFAULT ON** 2026-07-06 (user decision — verified via ladder-match corrections rather
than an A/B; the kill-switches remain for a one-line revert). The switch-OFF tests below therefore
disable the switch explicitly.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


# ============================================================ 83667237-107 — Prize-Redundant Target

@pytest.mark.req("REQ-READ-0001")
def test_107_body_identity_keying_plugs_the_duplicate_species_path_leak():
    """`path_target_ids` is CARD-ID keyed, so on-path credit leaks onto a duplicate-species copy;
    `_target_on_path` matches the specific BODY identity (`path_target_keys`) instead."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    bench_mega = select["option"][1]      # opp Mega Lucario ex, bench 1 (the redundant copy)
    makuhita = select["option"][3]        # opp Makuhita, bench 3 (the rider-reachable on-path small)
    lunatone = select["option"][0]        # opp Lunatone, bench 0 (off-path now — rider can't finish it)
    assert pilot._context(obs, select, board, bench_mega).target_on_path is False   # leak plugged
    assert pilot._context(obs, select, board, makuhita).target_on_path is True
    assert pilot._context(obs, select, board, lunatone).target_on_path is False     # grill flip


@pytest.mark.req("REQ-READ-0001")
def test_107_off_committed_path_bodies_are_flagged_redundant_when_safe():
    """Chip on a body OFF the committed cheapest path does not advance it. My Active is not doomed
    here — under pressure the guard would keep threat-denial instead."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    assert board.my_path_turns is not None and board.active_doomed is False        # safe, committed path
    assert pilot._context(obs, select, board, select["option"][1]).target_prize_redundant is True   # 2nd Mega
    assert pilot._context(obs, select, board, select["option"][0]).target_prize_redundant is True   # off-path Lunatone
    assert pilot._context(obs, select, board, select["option"][3]).target_prize_redundant is False  # Makuhita (on-path)


@pytest.mark.req("REQ-READ-0002")
def test_107_prize_redundant_suppresses_the_threat_snipe_hypotheses():
    """Chip on a body I never need to KO is wasted, so threat rank defers to the prize trajectory."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    d = pilot.explain(obs)
    fired = {h.id for h, _w in d.options[1].fired}                 # the redundant benched Mega
    assert "snipe-the-top-threat" not in fired and "snipe-the-threat" not in fired


@pytest.mark.req("REQ-READ-0002")
def test_107_opponent_discard_energy_is_read():
    """`Board.opp_discard_energy` is pure DATA — no live decider consumes it yet; the discard-fuel
    gauge's threat-rank lift awaits a corpus anchor."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    board = pilot._board(fx["obs"], fx["obs"]["select"])
    assert dict(board.opp_discard_energy) == {6: 5}      # {F} x5 (EnergyType.FIGHTING == 6)


@pytest.mark.req("REQ-READ-0002")
def test_107_snipes_an_on_path_small_not_the_redundant_second_mega():
    """The +1 prize lands on the RIDER-REACHABLE small, which the repeatable rider finishes alongside
    my main KOs — not on a body needing a dedicated gust-up (`snipe_prize_reach`)."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    assert pilot.snipe_prize_redundant is True           # DEFAULT ON (2026-07-06)
    assert pilot.snipe_prize_reach is True               # DEFAULT ON (snipe grill, 2026-07-21)
    d = pilot.explain(fx["obs"])
    assert d.chosen != fx["chosen"]        # not the old blunder [1] (the 2nd Mega Lucario ex)
    assert d.chosen == [3]                 # Makuhita — the rider-reachable on-path small (the grill fix)


@pytest.mark.req("REQ-READ-0003")
def test_107_kill_switch_off_reproduces_the_pre_adr_0044_pick():
    """OFF, `_target_on_path` keeps card-id keying and nothing is flagged redundant."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = False                  # kill-switch OFF (default is now ON)
    d = pilot.explain(fx["obs"])
    assert d.chosen == fx["chosen"]                       # unchanged: the pre-ADR-0044 behavior


# ============================================================ 83661649-45 — Forced-Promotion Read

@pytest.mark.req("REQ-READ-0004")
def test_45_opp_active_doomed_only_when_their_active_is_dead():
    """The read never fires while they still have a live attacker up."""
    pilot = _shipped_pilot()
    fx45 = _fx("planner_83661649_45.json")
    assert pilot._board(fx45["obs"], fx45["obs"]["select"]).opp_active_doomed is True
    fx107 = _fx("planner_83667237_107.json")
    assert pilot._board(fx107["obs"], fx107["obs"]["select"]).opp_active_doomed is False


@pytest.mark.req("REQ-READ-0004")
def test_45_forced_promotion_key_predicts_the_ready_wincon_not_the_energized_staryu():
    """The prediction is their highest OWN-damage READY attacker, not whichever body merely carries
    Energy now."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    mega = pilot._option_pokemon(obs, select, select["option"][1])    # benched Mega Starmie ex (430 HP)
    staryu = pilot._option_pokemon(obs, select, select["option"][0])  # energized Staryu (70 HP)
    assert board.forced_promotion_key == id(mega)
    assert board.forced_promotion_key != id(staryu)


@pytest.mark.req("REQ-READ-0005")
def test_45_forced_promotion_redirects_the_snipe_and_suppresses_the_mirage_via_the_scalar():
    """The mirage is suppressed by ZEROING `imminence`, which collapses the whole conjunctive product
    rather than out-ranking it; `forced` must DOMINATE its own imminence (ADR-0085)."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    assert pilot.snipe_relevance is True                  # shipped ARMED — the path under test
    pilot.forced_promotion = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    terms = [pilot._snipe_relevance_terms(obs, select, board, o,
                                          pilot._context(obs, select, board, o))
             for o in select["option"]]
    staryu, mega = terms[0], terms[1]
    # the mirage: zeroed at the source, so the product is zero however good our route is
    assert staryu["imminence"] == 0.0
    assert staryu["their_plan"] == 0.0
    assert staryu["relevance"] == 0.0
    assert staryu["my_route"] > 0.0                       # a live route, still worth nothing to snipe
    # the ready wincon: the forced leg carries it, and outranks its own discounted imminence
    assert mega["forced"] > 0.0
    assert mega["forced"] > mega["imminence"]
    assert mega["their_plan"] == pytest.approx(mega["forced"] * mega["brief_multiplier"])
    assert mega["relevance"] > staryu["relevance"]


@pytest.mark.req("REQ-READ-0005")
def test_45_pre_chips_the_ready_wincon_they_will_promote():
    """Chip the body they will be FORCED to promote, not the one that merely carries Energy."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    assert pilot.forced_promotion is True                # DEFAULT ON (2026-07-06)
    d = pilot.explain(fx["obs"])
    assert d.chosen == fx["correct"]                     # [1] the ready wincon, not the Staryu [0]


@pytest.mark.req("REQ-READ-0006")
def test_45_kill_switch_off_and_healthy_active_are_silent():
    """With the read ON but no promotion forced, the energized-imminence heuristic is untouched."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    pilot.forced_promotion = False                           # kill-switch OFF (default is now ON)
    assert pilot.explain(fx["obs"]).chosen == fx["chosen"]   # [0] energized Staryu — pre-ADR-0044
    pilot.forced_promotion = True                            # switch on, but opponent Active alive
    fx107 = _fx("planner_83667237_107.json")
    obs = fx107["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    assert all(not pilot._context(obs, select, board, o).target_is_forced_promotion
               for o in select["option"])
