"""The resolver's opponent DENY leg (keep-value v2 thread 2; the grill's Round-3 ruling).

`pilot._resolve_needs` emits DENY slots for the opponent's IN-PLAY bodies from VISIBLE facts only.
VALUE = the disruption CARD-tier (`TAG_TIER["gust"]` ≈ 10 in the ONE currency — the grill's
currency ruling, 2026-07-20), GRADED by the ruled basic lookahead (`_opp_turns_to_ready` →
`needs.turns_to_ready`: energy deficit at the 1-attach/turn quota, rules.md §3, in parallel with
the forward evolution hops still owed, rules.md §4). The shipped ADR-0062 oracle (`_denial_at`) is
now a GATE only (`> 0` = the strip bites this body); its DAMAGE magnitude (~140) stays on the
play-side gust rungs, never the keep price. Eligibility routes through the `needs.SUPPLIES` net (the
deny-supplying tags: gust / energy_denial), so the Hammer/gust classes stop riding the WP-N3 hedge.
Fail-closed everywhere: unknown stats, absent opponent read, a strip that bites nothing, or no
deny-capable held row → NO slot (the shipped hedge keeps pricing those rows).

Synthetic boards mirror `test_discard_shadow._setup`; the captured-board case replays a REAL
recorded correction through the real shipped pilot (`test_gust_round0_corpus` pattern — fresh
pilot per replay, the statefulness lesson).
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

from common import needs
from common.card_worth import TAG_TIER
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
DISCARD = 8
MEGA, HAMMER, BOSS, FILLER = 1031, 1120, 1182, 999
RIOLU, MLUC = 677, 660


def _setup(hand_ids, *, opp_active=None, opp_bench=(), minc=1):
    """A forced Discard over ``hand_ids`` against a visible opponent board — the
    `test_discard_shadow` fixture shape plus the opponent side the deny leg reads. The Riolu →
    Mega Lucario ex forward line (single hop — rulebook Appendix 1) carries real attack records so
    the ADR-0062 oracle prices strips: Riolu {F}=30; Mega Lucario ex {F}=130 / {F}{F}=270."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        HAMMER: CardStat(HAMMER, name="Crushing Hammer", cardType=1),
        BOSS: CardStat(BOSS, name="Boss's Orders", cardType=3),
        FILLER: CardStat(FILLER, name="Filler", cardType=1),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,)),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22)),
    }, attacks={11: AttackStat(11, damage=30, cost=1),
                21: AttackStat(21, damage=130, cost=1), 22: AttackStat(22, damage=270, cost=2)})
    funcs = CardFunctions({HAMMER: ["energy_denial"], BOSS: ["gust"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    obs = {"current": {"players": [
                {"active": [None], "bench": [], "hand": hand},
                {"active": [opp_active], "bench": list(opp_bench)}],
                "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": minc, "maxCount": minc, "option": opts}}
    return pilot, obs


def _deny_slots(pilot, obs, board=None):
    board = board if board is not None else pilot._board(obs)
    rows, _ = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    slots, elig = pilot._resolve_needs(obs, board, rows)
    return rows, slots, elig, [(j, s) for j, s in enumerate(slots) if s.kind == "deny"]


# ============================================================ the visible lookahead helper
@pytest.mark.req("REQ-NEEDS-0002")
def test_opp_turns_to_ready_is_the_visible_parallel_lookahead():
    """`_opp_turns_to_ready`: max of the energy leg (the LINE's biggest-attack cost — max
    `maxDamageCost` over current + forward forms — minus attached, at 1 attach/turn) and the
    forward-hop leg (`evolvesFrom` name-chain depth, one evolve/turn). A banked Riolu (1 Energy,
    one hop to Mega Lucario ex whose Mega Brave costs 2) is ONE turn out on both legs; a powered
    Mega Lucario ex is ready NOW; an unknown body reads None — fail-closed, no deny slot."""
    pilot, _obs = _setup([HAMMER])
    assert pilot._opp_turns_to_ready({"id": RIOLU, "energies": [0]}) == 1
    assert pilot._opp_turns_to_ready({"id": RIOLU, "energies": []}) == 2      # 2 attaches owed
    assert pilot._opp_turns_to_ready({"id": MLUC, "energies": [0, 0]}) == 0   # ready now
    assert pilot._opp_turns_to_ready({"id": 424242, "energies": [0]}) is None
    assert pilot._opp_turns_to_ready(None) is None


# ============================================================ the deny leg in the resolver
@pytest.mark.req("REQ-NEEDS-0007")
def test_resolver_emits_a_graded_deny_slot_at_the_disruption_card_tier():
    """The graded Hammer, wired at the CURRENCY ruling: a banked opponent Riolu (1 Energy toward
    Mega Lucario ex) opens ONE deny slot — value = the disruption CARD-tier (`TAG_TIER["gust"]` =
    10), graded by turns-to-ready (1 turn out → halved to 5.0, `needs.deny_slot`), NOT the ADR-0062
    damage swing. The oracle only GATES (the strip bites). ONLY the deny-supplying rows
    (energy_denial Hammer, gust Boss's) are eligible, via the `needs.SUPPLIES` net."""
    pilot, obs = _setup([HAMMER, FILLER, BOSS],
                        opp_active={"id": RIOLU, "hp": 70, "energies": [0]})
    rows, slots, elig, denys = _deny_slots(pilot, obs)
    assert len(denys) == 1
    j, slot = denys[0]
    assert slot.value == pytest.approx(TAG_TIER["gust"] / 2.0) and slot.deadline == 1  # 10 / 2¹
    suppliers = [rows[k]["cid"] for k in range(len(rows)) if j in elig[k]]
    assert sorted(suppliers) == [HAMMER, BOSS]                # the FILLER is never deny-eligible
    # the deny credit reaches keep_v2 through the assignment (sets-not-sums: with the Boss's also
    # covering, the Hammer's solo marginal is the Boss's displaced next-best slot, not the full 5.0)
    keeps, pick = pilot._needs_v2(obs, pilot._board(obs), rows, 1)
    assert keeps[0] > 0.0 and pick == [1]                     # the filler sheds, never the Hammer


@pytest.mark.req("REQ-NEEDS-0007")
def test_deny_leg_is_fail_closed():
    """Every unknown reads as NO slot (erring toward the shipped hedge): an unknown-stats body, a
    surplus-Energy body (the ADR-0062 whiff — stripping denies 0), an absent opponent read, and a
    hand with no deny-capable row each emit nothing."""
    # unknown body id -> `_opp_turns_to_ready` is None -> no slot
    pilot, obs = _setup([HAMMER], opp_active={"id": 424242, "energies": [0]})
    assert _deny_slots(pilot, obs)[3] == []
    # surplus Energy: Mega Lucario ex on 3 Energy still affords Mega Brave after a strip -> 0-priced
    pilot, obs = _setup([HAMMER], opp_active={"id": MLUC, "hp": 340, "energies": [0, 0, 0]})
    assert _deny_slots(pilot, obs)[3] == []
    # no opponent board at all
    pilot, obs = _setup([HAMMER])
    assert _deny_slots(pilot, obs)[3] == []
    # no deny-capable held row: the same juicy target, but nothing in hand supplies deny
    pilot, obs = _setup([FILLER, MEGA], opp_active={"id": RIOLU, "hp": 70, "energies": [0]})
    assert _deny_slots(pilot, obs)[3] == []


@pytest.mark.req("REQ-NEEDS-0007")
def test_deny_drops_the_doomed_active_and_grades_by_timing():
    """The `active_can_ko` drop, consumed intact: with my Active able to KO theirs the doomed Active
    denies nothing and emits NO slot, while every biting body still opens a card-tier slot graded by
    its OWN turns-to-ready — the ready Mega Lucario ex Active at the full band (10 / 2⁰), the banked
    bench Riolu one turn out at half (10 / 2¹). Bench vs Active is now a TIMING grade, not a fixed
    weight (the damage-model `_DENIAL_BENCH` discount is retired from the keep price)."""
    bench_body = {"id": RIOLU, "hp": 70, "energies": [0]}
    pilot, obs = _setup([HAMMER], opp_active={"id": MLUC, "hp": 340, "energies": [0, 0]},
                        opp_bench=[bench_body])
    board = pilot._board(obs)
    _rows, _slots, _elig, denys = _deny_slots(pilot, obs, board)
    by_key = {s.key: s for _j, s in denys}
    assert set(by_key) == {f"deny:active0:{MLUC}", f"deny:bench0:{RIOLU}"}
    assert by_key[f"deny:active0:{MLUC}"].value == pytest.approx(TAG_TIER["gust"])        # ready → 10
    assert by_key[f"deny:bench0:{RIOLU}"].value == pytest.approx(TAG_TIER["gust"] / 2.0)  # 1 out → 5
    doomed = dataclasses.replace(board, active_can_ko=True)
    _rows, _slots, _elig, denys = _deny_slots(pilot, obs, doomed)
    assert [s.key for _j, s in denys] == [f"deny:bench0:{RIOLU}"]
    assert denys[0][1].value == pytest.approx(TAG_TIER["gust"] / 2.0)


@pytest.mark.req("REQ-NEEDS-0007")
def test_deny_prices_a_far_threat_below_the_cards_general_worth():
    """The currency ruling on a REAL recorded board (82867148-48, mega_starmie): the held Boss's
    Orders (gust-tagged) never towers over its own general worth (4.5), whether priced through the
    pre-ADR-0074 `deny` route (a card-tier value graded down for distance) or — the armed default
    now — its own `gust_target` slot (the real per-body marginal, ADR-0074): either way the
    DECIDED pick stays unmoved (the discard corpus stays 12/12; `keep_v2` is unchanged at 4.5,
    its general floor). Under the pre-ruling damage-denominated value the same board priced the
    strip at 35/4 ≈ 8.8 and lifted the Boss's above everything — the exact over-pricing the
    original ruling retired, and the ADR-0074 migration does not reopen."""
    rec = None
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == "82867148" and d.get("decision", {}).get("frame") == 48:
                rec = d                                      # last write wins
    if rec is None:
        pytest.skip("correction 82867148-48 not in data/corrections/")
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pilot = mod._build_pilot(rec["agent"])[0]                # fresh shipped pilot (stateful lesson)
    dec = pilot.explain(rec["obs"])
    s = dec.discard_shadow
    assert s is not None and s["agree_v2"] is True           # the decided pick is unmoved
    board = pilot._board(rec["obs"])
    rows, _ = pilot._discard_equation_rows(rec["obs"], rec["obs"]["select"], board,
                                           rec["obs"]["select"]["option"])
    slots, _elig = pilot._resolve_needs(rec["obs"], board, rows)
    gust_target = [x for x in slots if x.kind == "gust_target"]
    assert gust_target and max(x.value for x in gust_target) < 4.5   # well below the general floor
    boss = next(r for r in s["eq"] if r["cid"] == BOSS)
    assert boss["keep_v2"] == pytest.approx(4.5)             # its general floor — the strip is below it
