"""The GUST-TARGET slot leg of the resolver (ADR-0076).

`_resolve_needs` emits `gust_target` slots for the opponent's BENCH bodies only — a gust forces a
switch of a BENCHED Pokémon, never the Active — gated by the `gust_target_slots` kill-switch, which
runtime.PROFILE arms. With it OFF, gust-tagged cards route through `deny`; both paths are asserted.

The `deny` read (ADR-0080) prices an Energy against a cost's TYPED slots, which is why the bodies
here hold real Basic {F} Energy and the attack records declare `energyTypes`.
"""
from __future__ import annotations

import pytest

from common import currency, needs
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

DISCARD = 8
MEGA, HAMMER, BOSS, FILLER = 1031, 1120, 1182, 999
RIOLU = 677
FIGHTING = 6                # EnergyType.FIGHTING (cg/api.py)
FIGHTING_ENERGY = 6         # Basic {F} Energy (SVE 6) — card id and type coincide by coincidence


def _banked(cid: int, hp: int, n: int = 1) -> dict:
    """An opponent bench body holding ``n`` real Basic {F} Energy cards: the armed deny read scores
    an untyped placeholder at 0, so `energies: [0]` would mean "holding nothing that matters"."""
    return {"id": cid, "hp": hp, "energies": [FIGHTING_ENERGY] * n}


def _setup(hand_ids, *, opp_bench=(), gust_target_slots=False):
    """MY Active vs an opponent BENCH, with a real `ma` so `_opponent_target_rows` has something to
    compute against. Riolu's Accelerating Stab is {F} for 30 (data/EN_Card_Data.csv)."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        HAMMER: CardStat(HAMMER, name="Crushing Hammer", cardType=1),
        BOSS: CardStat(BOSS, synthetic=True, name="Boss's Orders", cardType=3),
        FILLER: CardStat(FILLER, synthetic=True, name="Filler", cardType=1),
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,)),
        FIGHTING_ENERGY: CardStat(FIGHTING_ENERGY, name="Basic {F} Energy", energyType=FIGHTING),
    }, attacks={11: AttackStat(11, damage=30, cost=1, energyTypes=(FIGHTING,))})
    funcs = CardFunctions({HAMMER: ["energy_denial"], BOSS: ["gust"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs, gust_target_slots=gust_target_slots,
                  deny_relevance=True, deny_strip_delta=True)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    obs = {"current": {"players": [
                {"active": [{"id": MEGA, "hp": 330, "energies": []}], "bench": [], "hand": hand},
                {"active": [None], "bench": list(opp_bench)}],
                "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": 1, "maxCount": 1, "option": opts}}
    return pilot, obs


def _slots(pilot, obs):
    board = pilot._board(obs)
    rows = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    slots, elig = pilot._resolve_needs(obs, board, rows)
    by_kind = lambda kind: [(j, s) for j, s in enumerate(slots) if s.kind == kind]
    return rows, slots, elig, by_kind("deny"), by_kind("gust_target")


@pytest.mark.req("REQ-NEEDS-0011")
def test_off_routes_gust_through_deny_exactly_as_shipped():
    """The ROUTING is the claim; `test_needs_deny_resolver.py` owns what the `deny` slot is WORTH."""
    pilot, obs = _setup([BOSS], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=False)
    _rows, _slots_, _elig, denys, gusts = _slots(pilot, obs)
    assert len(denys) == 1 and gusts == []


@pytest.mark.req("REQ-NEEDS-0011")
def test_on_routes_gust_to_its_own_kind_instead_of_deny():
    """Armed: the SAME held Boss's Orders no longer opens a `deny` slot for that body — it opens a
    `gust_target` slot instead, valued by the real per-body removal value, never both at once."""
    pilot, obs = _setup([BOSS], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=True)
    _rows, _slots_, elig, denys, gusts = _slots(pilot, obs)
    assert denys == []
    assert len(gusts) == 1
    j, slot = gusts[0]
    assert slot.key == f"gust_target:bench0:{RIOLU}" and slot.deadline == 0 and slot.value > 0
    assert j in elig[0]                         # the Boss's Orders (row 0) supplies this slot
                                                 # (it may ALSO carry its own general-worth slot)


@pytest.mark.req("REQ-NEEDS-0011")
def test_on_still_denies_true_energy_denial_cards_unaffected():
    """Armed: a Hammer (`energy_denial`-tagged, not `gust`) is untouched by the migration — it still
    opens a `deny` slot exactly as before, since only the `gust` tag's routing moved."""
    pilot, obs = _setup([HAMMER], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=True)
    _rows, _slots_, _elig, denys, gusts = _slots(pilot, obs)
    assert len(denys) == 1 and gusts == []


@pytest.mark.req("REQ-NEEDS-0011")
def test_on_opens_no_gust_target_slot_with_no_gust_supplier_held():
    """Fail-closed: armed, but the hand holds no gust-tagged row (a Filler) — no slot, no crash."""
    pilot, obs = _setup([FILLER], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=True)
    _rows, _slots_, _elig, denys, gusts = _slots(pilot, obs)
    assert denys == [] and gusts == []


@pytest.mark.req("REQ-NEEDS-0011")
def test_the_emitted_slot_is_worth_denominated_not_prize_denominated():
    """The row's `value` is PRIZE-equivalents while every other slot is CARD-WORTH, so the emission
    must cross at `currency.target_value_to_worth`. Asserted as the crossing, never as a literal."""
    pilot, obs = _setup([BOSS], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=True)
    board = pilot._board(obs)
    row = next(r for r in pilot._deny_rows(obs, board) if r["area"] == "bench")
    _rows, _slots_, _elig, _denys, gusts = _slots(pilot, obs)

    assert len(gusts) == 1
    _j, slot = gusts[0]
    assert slot.value == pytest.approx(currency.target_value_to_worth(row["value"]))
    assert slot.value != pytest.approx(row["value"])      # the raw prize-equivalent is NOT emitted
    assert slot.value <= currency.GUST_TARGET_BAND        # ...and the band is a real ceiling


@pytest.mark.req("REQ-NEEDS-0012")
def test_the_per_body_value_resolves_once_per_decision_and_is_shared():
    """`_board()` resolves `_opponent_target_rows` ONCE per decision; the cost the cache avoids is a
    per-body `turns_to_ko_me` simulation."""
    pilot, obs = _setup([BOSS], opp_bench=[_banked(RIOLU, 70)],
                        gust_target_slots=True)
    board = pilot._board(obs)
    assert pilot._opponent_target_cache is not None
    cached_phase, cached_rows = pilot._opponent_target_cache
    assert cached_rows and cached_rows[0]["id"] == RIOLU

    calls = []
    real = pilot._opponent_target_rows

    def _spy(o, b):
        calls.append(1)
        return real(o, b)
    pilot._opponent_target_rows = _spy

    rows = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    slots, _elig = pilot._resolve_needs(obs, board, rows)

    assert not calls                            # the emission did not recompute — it read the cache
    gust = [x for x in slots if x.kind == "gust_target"]
    assert gust and cached_rows[0]["id"] == RIOLU


@pytest.mark.req("REQ-NEEDS-0016")
def test_the_gust_slot_survives_the_rollout_because_the_shared_rows_now_run_mid_sim():
    """ADR-0093 decision 6. Asserted as an IDENTITY between the two `_planning` states: the agent
    must score this the same inside its own rollout as outside it."""
    pilot, obs = _setup([BOSS], opp_bench=[{"id": RIOLU, "hp": 70, "energies": []}],
                        gust_target_slots=True)

    pilot._planning = False
    _rows, _slots_r, _elig, _deny, root_gust = _slots(pilot, obs)
    assert root_gust, "the fixture must offer a gust_target slot at the root, or it tests nothing"

    pilot._opponent_target_cache = None          # a rollout step starts with no per-decision cache
    pilot._planning = True
    _rows, _slots_m, _elig, _deny, mid_gust = _slots(pilot, obs)

    assert [s.value for _j, s in mid_gust] == [s.value for _j, s in root_gust], (
        f"gust emitted {[s.value for _j, s in mid_gust]} mid-sim but "
        f"{[s.value for _j, s in root_gust]} at the root — a shipped instrument going silent inside "
        f"the agent's own rollout")
