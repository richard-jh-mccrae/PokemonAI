"""The three keep-value v2 slot-CURRENCY rulings (grill session 2026-07-20) — pinned on the real
captured frames the user adjudicated. All three land INSIDE the one assignment equation as changes
to how slot VALUES derive from the board; no new gates/rungs/flags. Through the SHIPPED Pilot on the
committed corpus (`tune._build_pilot` — the strict retest bar; a fresh Pilot per frame, stateful).

  1. Answer-doom is not a flat tier: the switch/heal rescue prices at the DOOMED BODY'S own worth,
     and the successor rides an URGENT (full-tier, this-turn) succession slot — not the flat 20.
  2. A duplicate of a saturating-need Supporter is worth 0 (the spare fills nothing; you lose it in
     a shuffle for free).
  3. A held disruption card's slot is never the ADR-0062 DAMAGE swing (~140) — the damage math
     stays on the play-side gust rungs. Originally ruled for the `deny` slot at the disruption
     CARD-tier (~10); since ADR-0076 a gust-tagged card routes to its own `gust_target` kind at
     the per-body marginal instead, so the third test now pins that route. The card-tier `deny`
     value itself is still pinned (synthetically) in `test_needs.py` and
     `test_needs_deny_resolver.py`, which remain the deny leg's home.
"""
import sys
from pathlib import Path

import pytest

from poc_t4_flips import record_reason

from common import currency

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _corpus_frame(ep, fr):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    return corpus_record(ep, fr)


def _refresh_hand_slots(pilot, obs, exclude_cid):
    board = pilot._board_hypothetical(obs)
    rows = pilot._needs_hand_rows(obs, board, exclude_cid=exclude_cid)
    slots, elig = pilot._resolve_needs(obs, board, rows)
    return board, rows, slots, elig


@pytest.mark.req("REQ-NEEDS-0009")
def test_answer_doom_prices_the_switch_by_the_doomed_bodys_worth():
    """The answer-doom slot is valued at the DOOMED BODY'S own preserved worth — not a flat
    `clutch_heal` tier, and not the rescuing card's catalog worth."""
    pilot = _shipped_pilot("mega_lucario")
    obs = _corpus_frame("83661652", 40).obs
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
    """A doomed wincon's successor in hand takes a FULL-tier succession slot at deadline 0, so
    shuffling it away is expensive and the refresh swing goes NEGATIVE."""
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83037962", 49).obs
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)  # exclude the played Harlequin
    succ = [s for s in slots if s.key.endswith(":succ")]
    assert succ and succ[0].value == pytest.approx(30.0) and succ[0].deadline == 0
    # …and the LIVE swing (the v2 shed decides since ADR-0101) is negative: don't Harlequin.
    from types import SimpleNamespace

    from common.strategy.context import _PLAY
    board = pilot._board_hypothetical(obs)
    ctx = SimpleNamespace(card_id=1223, option_type=_PLAY)
    assert pilot._refresh_swing_tactical(obs, board, ctx) < 0.0


@pytest.mark.req("REQ-NEEDS-0009")
def test_duplicate_supporter_second_copy_is_worth_zero():
    """A recovery heal is NOT a draw engine, so it takes a DE-DUPLICATED general-worth slot: the
    spare copy covers nothing the first does not and prices 0."""
    from common import needs
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("82522698", 36).obs
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)
    wally_rows = [k for k, r in enumerate(rows) if r["cid"] == 1229]
    assert len(wally_rows) == 2, "the frame holds two Wally's"
    resupply = [0.0] * len(slots)
    keeps = [needs.keep_v2(slots, elig, resupply, k) for k in wally_rows]
    assert min(keeps) == pytest.approx(0.0)                     # the spare copy is worth 0
    # ONE de-duplicated general slot covers the Wally's class (recovery worth, not a draw engine),
    # which is WHY the spare prices 0 — the sibling already covers it.
    assert len([s for s in slots if s.key == "general:1229"]) == 1


@pytest.mark.req("REQ-NEEDS-0009")
def test_a_held_gust_cards_slot_is_never_the_damage_swing():
    """A held gust card's slot is the per-body removal marginal (prize-equivalents), NEVER the
    ADR-0062 damage swing: the damage math stays on the PLAY side."""
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83457493", 31).obs
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)
    gust_target = [s for s in slots if s.kind == "gust_target"]
    assert gust_target, "a fueled opponent bench opens gust_target slots (armed default, ADR-0076)"
    # Bounded against the mechanism's OWN ceiling, not a hand-fitted number: `target_value_to_worth`
    # clamps at `TARGET_VALUE_CEILING`, so `GUST_TARGET_BAND` is the maximum by construction.
    assert max(s.value for s in gust_target) <= currency.GUST_TARGET_BAND
    # ...and the claim the test is actually named for, stated as the order-of-magnitude gap it is.
    assert max(s.value for s in gust_target) < 140 / 10
    d = pilot.explain(obs)
    assert 4 in d.chosen                                        # plays Harlequin (correction [4])


@pytest.mark.xfail(strict=True, reason=record_reason("83969481", 55))
@pytest.mark.req("REQ-NEEDS-0009")
def test_a_heal_insuring_the_last_wincon_is_not_latent_worth():
    """A heal insuring the LAST playable wincon is the survival plan, not latent worth, so it takes
    an INSURANCE slot at full tier rather than the general-worth haircut."""
    from types import SimpleNamespace

    from common.strategy.context import _PLAY
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83969481", 55).obs
    board = pilot._board_hypothetical(obs)
    assert not board.active_doomed, "the premise: NOT doomed this turn — answer_doom must stay shut"
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1227)
    insure = [s for s in slots if s.key == "insure:1229"]
    assert insure and insure[0].value == pytest.approx(20.0) and insure[0].deadline == 1
    assert not [s for s in slots if s.key == "general:1229"], "the latency haircut must not ALSO fire"
    ctx = SimpleNamespace(card_id=1227, option_type=_PLAY)
    assert pilot._refresh_swing_tactical(obs, board, ctx) < 0.0    # the refresh is declined
    assert 4 in pilot.explain(obs).chosen                          # …and the agent attacks


@pytest.mark.req("REQ-NEEDS-0009")
def test_the_insurance_slot_stands_down_when_a_second_wincon_is_in_play():
    """Same card, tag and undoomed Active as the frame above — only the successor's existence
    differs, which is the fact the slot is keyed on."""
    pilot = _shipped_pilot("mega_starmie")
    obs = _corpus_frame("83661649", 30).obs
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1223)
    assert [s for s in slots if s.key == "general:1229"], "the heal keeps its latent-worth slot"
    assert not [s for s in slots if s.key.startswith("insure:")], "nothing irreplaceable to insure"


@pytest.mark.req("REQ-NEEDS-0009")
def test_the_insurance_slot_reads_copies_remaining_not_board_shape():
    """"Our LAST wincon" is a claim about COPIES REMAINING, not about an empty Bench — an empty Bench
    under a knock-outable Active already has `empty-bench-filter` and `_predicted_loss`."""
    pilot = _shipped_pilot("mega_starmie")
    rec = _corpus_frame("82525101", 87)
    obs = rec.obs
    board = pilot._board_hypothetical(obs)
    me = pilot._my_player(obs)
    assert board.my_bench == 0 and not board.active_doomed      # the same shape as f55…
    held = [c["id"] for c in (me.get("hand") or []) if c and c.get("id") is not None]
    assert 1229 in held, "the fixture holds a Wally's Compassion"
    # …but the line is REBUILDABLE, so the insurance slot must stand down
    assert not pilot._heal_insures_the_last_wincon(1229, me)
    _, rows, slots, elig = _refresh_hand_slots(pilot, obs, exclude_cid=1227)
    assert not [s for s in slots if s.key.startswith("insure:")]
    assert set(rec.correct) <= set(pilot.explain(obs).chosen)
