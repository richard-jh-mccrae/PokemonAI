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
    """The opponent fields TWO Mega Lucario ex sharing card-id 678 — the ACTIVE (on my cheapest
    path) and a benched redundant copy. `path_target_ids` is card-id-keyed, so the on-path credit
    leaks onto the benched copy. Under `snipe_prize_redundant`, `_target_on_path` matches the
    specific BODY identity (`path_target_keys`), so the benched 678 reads OFF-path while a genuinely
    on-path small (Lunatone, bench 0) reads on-path."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    bench_mega = select["option"][1]      # opp Mega Lucario ex, bench 1 (the redundant copy)
    lunatone = select["option"][0]        # opp Lunatone, bench 0 (a genuine on-path small)
    assert pilot._context(obs, select, board, bench_mega).target_on_path is False   # leak plugged
    assert pilot._context(obs, select, board, lunatone).target_on_path is True


@pytest.mark.req("REQ-READ-0001")
def test_107_off_committed_path_bodies_are_flagged_redundant_when_safe():
    """The prize-trajectory read: I need 4 prizes and have a COMMITTED cheapest path (the active Mega
    + the on-path small Lunatone). Chip on any body OFF that path doesn't advance it — the second Mega
    Lucario ex (3 prizes I never need) and the alternative small Makuhita are both flagged
    `target_prize_redundant`; the on-path Lunatone is not. (My Active is not doomed here, so even the
    low-prize off-path body is deprioritized — under pressure the guard would keep threat-denial.)"""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = True
    obs = fx["obs"]
    select = obs["select"]
    board = pilot._board(obs, select)
    assert board.my_path_turns is not None and board.active_doomed is False        # safe, committed path
    assert pilot._context(obs, select, board, select["option"][1]).target_prize_redundant is True   # 2nd Mega
    assert pilot._context(obs, select, board, select["option"][3]).target_prize_redundant is True   # off-path Makuhita
    assert pilot._context(obs, select, board, select["option"][0]).target_prize_redundant is False  # Lunatone (on-path)


@pytest.mark.req("REQ-READ-0002")
def test_107_prize_redundant_suppresses_the_threat_snipe_hypotheses():
    """A prize-redundant target does not attract `snipe-the-top-threat` / `snipe-the-threat`: chip
    on a body I don't need to KO is wasted, so the threat rank must defer to the prize trajectory."""
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
def test_107_snipes_an_on_path_small_not_the_redundant_second_mega():
    """End-to-end (ADR-0044): on the ACTUAL captured state the shipped Pilot no longer snipes the
    redundant second Mega Lucario ex — it chips the on-path 1-prize small (Lunatone), advancing my
    cheapest 4-prize path instead of wasting chip on a body I mean to gust around."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    assert pilot.snipe_prize_redundant is True           # DEFAULT ON (2026-07-06)
    d = pilot.explain(fx["obs"])
    assert d.chosen != fx["chosen"]        # not the old blunder [1] (the 2nd Mega Lucario ex)
    assert d.chosen == [0]                 # Lunatone — the on-path small (snipe-on-the-path)


@pytest.mark.req("REQ-READ-0003")
def test_107_kill_switch_off_reproduces_the_pre_adr_0044_pick():
    """The kill-switch still works: with it OFF (a manual override now the default is ON),
    `_target_on_path` keeps card-id keying and no target is flagged redundant, so the Pilot
    reproduces the pre-ADR-0044 pick — a one-line revert if a ladder correction demands it."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    pilot.snipe_prize_redundant = False                  # kill-switch OFF (default is now ON)
    d = pilot.explain(fx["obs"])
    assert d.chosen == fx["chosen"]                       # unchanged: the pre-ADR-0044 behavior


# ============================================================ 83661649-45 — Forced-Promotion Read

@pytest.mark.req("REQ-READ-0004")
def test_45_opp_active_doomed_only_when_their_active_is_dead():
    """The trigger: their Active is at 0 HP, so a promotion is forced next turn (opp_active_doomed).
    On a board where their Active is alive (the 107 state, a 200-HP Mega Lucario ex), it is False —
    the read never fires while they still have a live attacker up."""
    pilot = _shipped_pilot()
    fx45 = _fx("planner_83661649_45.json")
    assert pilot._board(fx45["obs"], fx45["obs"]["select"]).opp_active_doomed is True
    fx107 = _fx("planner_83667237_107.json")
    assert pilot._board(fx107["obs"], fx107["obs"]["select"]).opp_active_doomed is False


@pytest.mark.req("REQ-READ-0004")
def test_45_forced_promotion_key_predicts_the_ready_wincon_not_the_energized_staryu():
    """When forced to promote, the opponent brings up their highest OWN-damage ready attacker — the
    430-HP Mega Starmie ex — NOT the energized 70-HP Staryu that merely carries Energy now."""
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
def test_45_forced_promotion_redirects_the_snipe_and_suppresses_the_mirage():
    """With the read on: the energized Staryu is a promotion mirage (they won't bring it up), so its
    threat/imminence snipe is suppressed; the ready wincon gets `snipe-the-forced-promotion`."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    pilot.forced_promotion = True
    d = pilot.explain(fx["obs"])
    staryu_fired = {h.id for h, _w in d.options[0].fired}
    mega_fired = {h.id for h, _w in d.options[1].fired}
    assert "snipe-the-top-threat" not in staryu_fired and "snipe-the-threat" not in staryu_fired
    assert "snipe-the-forced-promotion" in mega_fired


@pytest.mark.req("REQ-READ-0005")
def test_45_pre_chips_the_ready_wincon_they_will_promote():
    """End-to-end (ADR-0044): on the ACTUAL captured state the shipped Pilot chips the benched Mega
    Starmie ex it will face next turn, not the energized Staryu they will never promote."""
    fx = _fx("planner_83661649_45.json")
    pilot = _shipped_pilot()
    assert pilot.forced_promotion is True                # DEFAULT ON (2026-07-06)
    d = pilot.explain(fx["obs"])
    assert d.chosen == fx["correct"]                     # [1] the ready wincon, not the Staryu [0]


@pytest.mark.req("REQ-READ-0006")
def test_45_kill_switch_off_and_healthy_active_are_silent():
    """The kill-switch OFF (a manual override now the default is ON) reproduces the pre-ADR-0044 pick;
    and with the read ON, a healthy opponent Active (107 state) yields no forced-promotion target —
    the energized-imminence heuristic is untouched when no promotion is forced."""
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
