"""The three keep-value v2 slot-CURRENCY rulings (grill session 2026-07-20) — pinned on the real
captured frames the user adjudicated. All three land INSIDE the one assignment equation as changes
to how slot VALUES derive from the board; no new gates/rungs/flags. Through the SHIPPED Pilot on the
committed corpus (`tune._build_pilot` — the strict retest bar; a fresh Pilot per frame, stateful).

  1. Answer-doom is not a flat tier: the switch/heal rescue prices at the DOOMED BODY'S own worth,
     and the successor rides an URGENT (full-tier, this-turn) succession slot — not the flat 20.
  2. A duplicate of a saturating-need Supporter is worth 0 (the spare fills nothing; you lose it in
     a shuffle for free).
  3. The deny slot is valued at the disruption CARD-tier (~10), never the ADR-0062 DAMAGE swing
     (~140) — the damage math stays on the play-side gust rungs.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _corpus_frame(ep, fr):
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == ep and d.get("decision", {}).get("frame") == fr:
                return d
    raise AssertionError(f"frame {ep}-{fr} not in the corpus")


def _refresh_hand_slots(pilot, obs, exclude_cid):
    board = pilot._board_hypothetical(obs)
    rows = pilot._needs_hand_rows(obs, board, exclude_cid=exclude_cid)
    slots, elig = pilot._resolve_needs(obs, board, rows)
    return board, rows, slots, elig


@pytest.mark.req("REQ-NEEDS-0009")
def test_answer_doom_prices_the_switch_by_the_doomed_bodys_worth():
    """ep83661652 f40 (Game A): my Lunatone (engine, worth 12) is doomed; a worth-0 Switch in hand
    rescues it. The answer-doom slot is valued at the DOOMED BODY'S own preserved worth (12), not a
    flat clutch_heal tier (20) and not the Switch's ~0 catalog worth — saving the engine is worth
    what the engine is worth. The correction plays the develop line, not the refresh."""
    pilot = _shipped_pilot("mega_lucario")
    obs = _corpus_frame("83661652", 40)["obs"]
    board = pilot._board_hypothetical(obs)
    assert board.active_doomed
    active_id = next(b["id"] for b in obs["current"]["players"][obs["current"]["yourIndex"]]["active"] if b)
    preserved = pilot._role_value(active_id)
    assert preserved == pytest.approx(12.0)                     # Lunatone's engine tier, verified
    # the resolver emits the answer-doom slot at exactly that preserved worth (not TAG_TIER 20)
    rows = [{"i": 0, "cid": 1123, "deploy": 1.0}]               # Switch (a `switch`-tagged card)
    slots, _ = pilot._resolve_needs(obs, board, rows)
    doom = [s for s in slots if s.kind == "answer_doom"]
    assert doom and doom[0].value == pytest.approx(preserved) and doom[0].value != 20.0


@pytest.mark.req("REQ-NEEDS-0009")
def test_doomed_successor_rides_a_full_tier_this_turn_succession_slot():
    """ep83037962 f49 (Game B): my Mega Starmie ex is doomed; the second copy in hand (its Staryu
    just benched) is the successor. It gets a FULL-tier (30) succession slot at deadline 0 — the old
    answer-doom successor spike re-derived — so shuffling it away (Harlequin) is expensive: the
    refresh shed prices the hand up and the refresh swing is NEGATIVE (don't Harlequin)."""
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83037962", 49)["obs"]
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)  # exclude the played Harlequin
    succ = [s for s in slots if s.key.endswith(":succ")]
    assert succ and succ[0].value == pytest.approx(30.0) and succ[0].deadline == 0
    s = pilot.explain(obs).refresh_shadow
    assert s is not None and s["cid"] == 1223 and s["swing_v2"] < 0.0  # the refresh is declined


@pytest.mark.req("REQ-NEEDS-0009")
def test_duplicate_supporter_second_copy_is_worth_zero():
    """ep82522698 f36 (Game C): two Wally's Compassion (a one-per-turn Supporter). One fills the
    saturating draw-engine need; the SPARE gets NO general slot and prices keep_v2 = 0 — "you lose
    the second Supporter in a shuffle for free". The whole-hand shed drops accordingly."""
    from common import needs
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("82522698", 36)["obs"]
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)
    wally_rows = [k for k, r in enumerate(rows) if r["cid"] == 1229]
    assert len(wally_rows) == 2, "the frame holds two Wally's"
    resupply = [0.0] * len(slots)
    keeps = [needs.keep_v2(slots, elig, resupply, k) for k in wally_rows]
    assert min(keeps) == pytest.approx(0.0)                     # the spare copy is worth 0
    # and no general slot exists for the (saturating-engine) Wally's class
    assert not [s for s in slots if s.key == "general:1229"]


@pytest.mark.req("REQ-NEEDS-0009")
def test_deny_slot_is_valued_at_card_tier_not_the_damage_swing():
    """ep83457493 f31 (Game D): the opponent's Mega Lucario ex is fully fueled; I hold Boss's Orders
    (gust). The deny slot is valued at the disruption CARD-tier (~10, graded by turns-to-ready), NOT
    the ADR-0062 DAMAGE swing (~140) — so Boss's is a good card, never a whole-hand anchor. The
    damage math stays on the play side; the correction plays Harlequin (the deny no longer towers)."""
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83457493", 31)["obs"]
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)
    deny = [s for s in slots if s.kind == "deny"]
    assert deny, "a fueled opponent body opens a deny slot"
    # every deny slot is card-tier magnitude (≤ the gust tier 10, graded down), never the ~140 swing
    assert max(s.value for s in deny) <= 10.0
    d = pilot.explain(obs)
    assert 4 in d.chosen                                        # plays Harlequin (correction [4])
