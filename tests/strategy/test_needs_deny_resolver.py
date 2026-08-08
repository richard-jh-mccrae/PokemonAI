"""The resolver's opponent DENY leg — ADR-0080 / Issue #187.

A deny slot is the disruption CARD-tier SCALED by that body's relevance (a ``[0, 1]`` scalar, so the
tier is a CEILING and never the play-side damage swing) and GRADED by `_opp_turns_to_ready`.
Fail-closed everywhere: unknown stats, no opponent read, a strip that bites nothing, or no
deny-capable held row all emit NO slot.
"""
from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from common import currency, needs
from common.card_worth import TAG_TIER
from common.cards import CardFunctions
from common.pilot import _DENIAL_FORWARD, _DENY_RELEVANCE_K, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
DISCARD = 8
MEGA, HAMMER, BOSS, FILLER, DREEPY = 1031, 1120, 1182, 999, 119   # Dreepy: 2 hops from Dragapult ex
RIOLU, MLUC = 677, 660
FIGHTING = 6                # EnergyType.FIGHTING (cg/api.py)
FIGHTING_ENERGY = 6         # Basic {F} Energy (SVE 6). Card id and EnergyType coincide by
                            # COINCIDENCE in the data — the read resolves the type through the
                            # Provider, never from the card id.


def _deny_value(setback_damage: float, turns: int) -> float:
    """``setback_damage`` is spelled out from CARD FACTS at each call site rather than read back off
    the pilot, so these tests pin the FORMULA instead of whatever the pilot computed."""
    return TAG_TIER["gust"] * (setback_damage / _DENY_RELEVANCE_K) / (2.0 ** turns)


def _setup(hand_ids, *, opp_active=None, opp_bench=(), minc=1):
    """Relevance is a function of an Energy's TYPE against a cost's typed slots, so every attack
    needs `energyTypes` and MY Active must exist — `_opponent_target_rows` returns nothing without it."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        HAMMER: CardStat(HAMMER, name="Crushing Hammer", cardType=1),
        BOSS: CardStat(BOSS, synthetic=True, name="Boss's Orders", cardType=3),
        FILLER: CardStat(FILLER, synthetic=True, name="Filler", cardType=1),
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,)),
        MLUC: CardStat(MLUC, synthetic=True, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22)),
        FIGHTING_ENERGY: CardStat(FIGHTING_ENERGY, name="Basic {F} Energy", energyType=FIGHTING),
    }, attacks={11: AttackStat(11, damage=30, cost=1, energyTypes=(FIGHTING,)),
                21: AttackStat(21, damage=130, cost=1, energyTypes=(FIGHTING,)),
                22: AttackStat(22, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING))})
    funcs = CardFunctions({HAMMER: ["energy_denial"], BOSS: ["gust"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  deny_relevance=True, deny_strip_delta=True,
                  functions=funcs)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    obs = {"current": {"players": [
                {"active": [{"id": MEGA, "hp": 330, "maxHp": 330, "energies": []}],
                 "bench": [], "hand": hand},
                {"active": [opp_active], "bench": list(opp_bench)}],
                "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": minc, "maxCount": minc, "option": opts}}
    return pilot, obs


def _energized(cid: int, hp: int, n: int = 1) -> dict:
    """An opponent body holding ``n`` real Basic {F} Energy cards."""
    return {"id": cid, "hp": hp, "energies": [FIGHTING_ENERGY] * n}


def _deny_slots(pilot, obs, board=None):
    board = board if board is not None else pilot._board(obs)
    rows = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    slots, elig = pilot._resolve_needs(obs, board, rows)
    return rows, slots, elig, [(j, s) for j, s in enumerate(slots) if s.kind == "deny"]


# ============================================================ the visible lookahead helper
@pytest.mark.req("REQ-NEEDS-0002")
def test_opp_turns_to_ready_is_the_visible_parallel_lookahead():
    """The MAX of the energy leg (the LINE's biggest-attack cost, at 1 attach/turn) and the
    forward-hop leg (`evolvesFrom` chain depth, 1 evolve/turn); an unknown body reads None."""
    pilot, _obs = _setup([HAMMER])
    pilot._snapshot(_obs)        # the clock reads THEIR side off the snapshot now (POC-T1)
    assert pilot._opp_turns_to_ready(None) is None       # …and None without a snapshot, likewise
    assert pilot._opp_turns_to_ready({"id": RIOLU, "energies": [0]}) == 1
    assert pilot._opp_turns_to_ready({"id": RIOLU, "energies": []}) == 2      # 2 attaches owed
    assert pilot._opp_turns_to_ready({"id": MLUC, "energies": [0, 0]}) == 0   # ready now
    assert pilot._opp_turns_to_ready({"id": 424242, "energies": [0]}) is None
    assert pilot._opp_turns_to_ready(None) is None


# ============================================================ the deny leg in the resolver
@pytest.mark.req("REQ-NEEDS-0007")
def test_resolver_emits_a_graded_deny_slot_at_the_disruption_card_tier():
    """Energy banked on a pre-evolution counts toward the evolved form's cost ("Evolving keeps
    attached cards", rules.md:98) at the `_DENIAL_FORWARD` discount, since the payoff is contingent."""
    pilot, obs = _setup([HAMMER, FILLER, BOSS], opp_active=_energized(RIOLU, 70))
    rows, slots, elig, denys = _deny_slots(pilot, obs)
    assert len(denys) == 1
    j, slot = denys[0]
    assert slot.value == pytest.approx(_deny_value(_DENIAL_FORWARD * 270, 1)) and slot.deadline == 1
    suppliers = [rows[k]["cid"] for k in range(len(rows)) if j in elig[k]]
    assert sorted(suppliers) == [HAMMER, BOSS]                # the FILLER is never deny-eligible
    # the deny credit reaches keep_v2 through the assignment (sets-not-sums: with the Boss's also
    # covering, the Hammer's solo marginal is the Boss's displaced next-best slot, not the full 5.0)
    keeps, pick = pilot._needs_v2(obs, pilot._board(obs), rows, 1)
    assert keeps[0] > 0.0 and pick == [1], (                  # the filler sheds, never the Hammer
        f"the deny credit must reach keep_v2 (keeps={keeps}, pick={pick})")


@pytest.mark.req("REQ-NEEDS-0007")
def test_deny_leg_is_fail_closed():
    """The whiff cases arrive STRUCTURALLY through relevance reaching 0 rather than through a
    separate predicate — surplus Energy puts no attack further out of reach."""
    # unknown body id -> `_opp_turns_to_ready` is None -> no slot
    pilot, obs = _setup([HAMMER], opp_active=_energized(424242, 0))
    assert _deny_slots(pilot, obs)[3] == []
    # surplus Energy: Mega Lucario ex on 3 Energy still affords Mega Brave after a strip -> 0-priced
    pilot, obs = _setup([HAMMER], opp_active=_energized(MLUC, 340, 3))
    assert _deny_slots(pilot, obs)[3] == []
    # no opponent board at all
    pilot, obs = _setup([HAMMER])
    assert _deny_slots(pilot, obs)[3] == []
    # no deny-capable held row: the same juicy target, but nothing in hand supplies deny
    pilot, obs = _setup([FILLER, MEGA], opp_active=_energized(RIOLU, 70))
    assert _deny_slots(pilot, obs)[3] == []


@pytest.mark.req("REQ-NEEDS-0007")
def test_deny_drops_the_doomed_active_and_grades_by_timing():
    """Bench vs Active is a TIMING grade, not an area term: nothing here is a fixed bench discount,
    and the deadlines below come from each body's own turns-to-ready."""
    pilot, obs = _setup([HAMMER], opp_active=_energized(MLUC, 340, 2),
                        opp_bench=[_energized(RIOLU, 70)])
    board = pilot._board(obs)
    _rows, _slots, _elig, denys = _deny_slots(pilot, obs, board)
    by_key = {s.key: s for _j, s in denys}
    assert set(by_key) == {f"deny:active0:{MLUC}", f"deny:bench0:{RIOLU}"}
    assert by_key[f"deny:active0:{MLUC}"].deadline == 0, "the ready Active is at the full band"
    assert by_key[f"deny:bench0:{RIOLU}"].deadline == 1, "the banked bench body is one turn out"
    assert by_key[f"deny:active0:{MLUC}"].value == pytest.approx(_deny_value(270, 0))
    assert by_key[f"deny:bench0:{RIOLU}"].value == pytest.approx(
        _deny_value(_DENIAL_FORWARD * 270, 1))
    doomed = dataclasses.replace(board, active_can_ko=True)
    _rows, _slots, _elig, denys = _deny_slots(pilot, obs, doomed)
    assert [s.key for _j, s in denys] == [f"deny:bench0:{RIOLU}"]
    assert denys[0][1].value == pytest.approx(_deny_value(_DENIAL_FORWARD * 270, 1))


@pytest.mark.req("REQ-NEEDS-0007")
def test_a_gust_cards_slot_prices_below_the_cards_general_worth():
    """A held gust card's slot must price UNDER the card's own general floor, so it never anchors the
    hand; asserted against the floor directly so it cannot go vacuous when the marginal moves."""
    # THE Corpus Reader (ADR-0087 / ADR-0089): it RAISES on a missing frame, where the inline walk
    # it replaced skipped — a green nobody can notice.
    from corpus_helpers import corpus_record
    rec = corpus_record("82867148", 48)
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pilot = mod._build_pilot(rec.agent)[0]                # fresh shipped pilot (stateful lesson)
    board = pilot._board(rec.obs)
    rows = pilot._discard_equation_rows(rec.obs, rec.obs["select"], board,
                                           rec.obs["select"]["option"])
    slots, _elig = pilot._resolve_needs(rec.obs, board, rows)
    gust_target = [x for x in slots if x.kind == "gust_target"]
    # EXACT, so the formula is pinned rather than bounded: the survival leg is 0 here, leaving the
    # whole marginal as `prize_advance` — the LINE's prize since ADR-0119, not the body's own.
    assert len(gust_target) == 1
    assert pilot.combat.forward_line_prize(DREEPY) == (2, 2), (
        "the premise of the number below — a two-hop line to a 2-prize ex, not a dead end")
    assert gust_target[0].value == pytest.approx(currency.target_value_to_worth(1.25))
    assert gust_target[0].value < 4.5                        # ...and so below the card's own floor
    keeps, _pick = pilot._needs_v2(rec.obs, board, rows, rec.obs["select"]["maxCount"])
    boss = next(k for r, k in zip(rows, keeps) if r["cid"] == BOSS)
    assert boss == pytest.approx(4.5)                        # its general floor — the strip is below it
    assert pilot.explain(rec.obs).chosen == _pick            # ...and the DECIDED pick is unmoved
