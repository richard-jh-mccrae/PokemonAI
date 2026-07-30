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
    on-path small reads on-path. Since the snipe-targeting grill (2026-07-21, `snipe_prize_reach`)
    the on-path small is MAKUHITA (bench 3, 80 HP) — the +1 prize my repeatable Jetting Blow rider
    (⌈80/50⌉=2) finishes alongside my main KOs — NOT Lunatone (110 HP, needs a dedicated gust-up)."""
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
    """The prize-trajectory read: I need 4 prizes and have a COMMITTED cheapest path (the active Mega
    + the on-path small). Chip on any body OFF that path doesn't advance it. Since the snipe grill
    (`snipe_prize_reach`) the committed small is MAKUHITA — the +1 my rider finishes for free — so
    Makuhita is NOT redundant while Lunatone (110 HP, off the rider-reachable path) and the second
    Mega Lucario ex (3 prizes I never need) both are. (My Active is not doomed here, so even the
    low-prize off-path body is deprioritized — under pressure the guard would keep threat-denial.)"""
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
def test_107_opponent_discard_energy_is_read():
    """Opponent-discard reading (coverage-review item #2, previously 'not read at all'): the
    opponent's fully-visible discard on 83667237-107 holds five Basic {F} Energy (EnergyType 6) —
    now surfaced as `Board.opp_discard_energy`, the raw read behind the discard-fuel gauge (the {F}
    that keeps the Hariyama Wild Press / Aura-Jab lines live). Pure data; no live decider consumes
    it yet (the gauge's threat-rank lift awaits a corpus anchor — 107 itself is prize-math)."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    board = pilot._board(fx["obs"], fx["obs"]["select"])
    assert dict(board.opp_discard_energy) == {6: 5}      # {F} x5 (EnergyType.FIGHTING == 6)


@pytest.mark.req("REQ-READ-0002")
def test_107_snipes_an_on_path_small_not_the_redundant_second_mega():
    """End-to-end (ADR-0044 + the 2026-07-21 snipe grill): on the ACTUAL captured state the shipped
    Pilot no longer snipes the redundant second Mega Lucario ex — it chips MAKUHITA (bench 3), the
    1-prize small my repeatable Jetting Blow rider (⌈80/50⌉=2) finishes alongside my main KOs, taking
    the 4th prize for free. NOT Lunatone (110 HP, needs a dedicated gust-up): the grill ruled the +1
    lands on the rider-reachable body, the user's `correct` on this frame (`snipe_prize_reach`)."""
    fx = _fx("planner_83667237_107.json")
    pilot = _shipped_pilot()
    assert pilot.snipe_prize_redundant is True           # DEFAULT ON (2026-07-06)
    assert pilot.snipe_prize_reach is True               # DEFAULT ON (snipe grill, 2026-07-21)
    d = pilot.explain(fx["obs"])
    assert d.chosen != fx["chosen"]        # not the old blunder [1] (the 2nd Mega Lucario ex)
    assert d.chosen == [3]                 # Makuhita — the rider-reachable on-path small (the grill fix)


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


# `test_45_..._via_the_rungs` was DELETED with the rungs it named (ADR-0085's deletion pass). It
# asserted REQ-READ-0005 through `snipe-the-top-threat` / `snipe-the-threat` / `snipe-the-forced-
# promotion` firing, and those hypotheses no longer exist. The requirement is unchanged and is
# carried by the `_via_the_scalar` sibling immediately below, which asserts the same two facts on the
# graded terms: the mirage zeroed at source, and the forced leg dominating its own imminence.

@pytest.mark.req("REQ-READ-0005")
def test_45_forced_promotion_redirects_the_snipe_and_suppresses_the_mirage_via_the_scalar():
    """The SAME requirement through the shipped ARMED instrument (ADR-0085, armed-ON 2026-07-30).

    The six additive target rungs stand down together when `snipe_relevance` is armed, so REQ-READ-0005
    can no longer be read off hypothesis IDs — it is carried by the graded terms instead, and this
    asserts it there so the requirement stays covered in the configuration that actually ships:

    * the mirage is suppressed by ZEROING `imminence` (ADR-0085's `target_promotion_mirage`), which
      collapses `their_plan` and with it the whole conjunctive product — not merely out-ranked;
    * the ready wincon earns the `forced` leg, and `forced` must DOMINATE its own `imminence` (the
      no-imminence-discount clause: a forced promotion is not discounted by how long they need).
    """
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
