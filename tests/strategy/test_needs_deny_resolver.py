"""The resolver's opponent DENY leg (keep-value v2 thread 2; the grill's Round-3 ruling).

`pilot._resolve_needs` emits DENY slots for the opponent's IN-PLAY bodies from VISIBLE facts only.
VALUE = the disruption CARD-tier (`TAG_TIER["gust"]` ≈ 10 in the ONE currency — the grill's
currency ruling, 2026-07-20) SCALED BY DENY RELEVANCE, then GRADED by the ruled basic lookahead
(`_opp_turns_to_ready` → `needs.turns_to_ready`: energy deficit at the 1-attach/turn quota,
rules.md §3, in parallel with the forward evolution hops still owed, rules.md §4). Eligibility
routes through the `needs.SUPPLIES` net (the deny-supplying tags: gust / energy_denial), so the
Hammer/gust classes stop riding the WP-N3 hedge. Fail-closed everywhere: unknown stats, absent
opponent read, a strip that bites nothing, or no deny-capable held row → NO slot (the shipped hedge
keeps pricing those rows).

**The instrument moved (ADR-0080 / Issue #187, armed and the incumbent DELETED by Issue #228).**
The ADR-0062 oracle (`_denial_at`) used to be a pure GATE here — `> 0` meant "the strip bites this
body" — and the card tier was then paid FLAT. Armed, the tier is multiplied by that body's
relevance, so a Hammer is worth keeping in proportion to how much the Energy it would take is
actually doing; the tier survives as the CEILING rather than the value. This is still not a damage
magnitude: relevance is a ``[0, 1]`` scalar, so the currency ruling ("never the play-side damage
swing on the keep price") is intact, which is the claim these tests carry. The gate survives too —
relevance is 0 for a bare body, for surplus Energy and for one dying to my KO this turn, so the
whiff cases below arrive structurally rather than through a separate predicate.

Two fixture consequences, named rather than discovered:
  * the read resolves an Energy's TYPE through the Stat Provider, so an opponent body must carry a
    real Basic ``{F}`` Energy **card id** and each attack must declare its per-slot cost types —
    a colourless placeholder is on no plan's critical path and scores 0;
  * the rows are built by `_opponent_target_rows`, which needs MY Active as well as theirs (its
    clock legs are differences of `turns_to_ko_me`). A board with an empty Active spot returns NO
    rows at all, where the old opponent-only oracle happily priced one.

boards mirror `test_discard_keep_rows._setup`; the captured-board case replays a REAL
recorded correction through the real shipped pilot (`test_gust_round0_corpus` pattern — fresh
pilot per replay, the statefulness lesson).
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
MEGA, HAMMER, BOSS, FILLER = 1031, 1120, 1182, 999
DREEPY = 119     # the corpus frame's only gustable body: two hops from Dragapult ex
RIOLU, MLUC = 677, 660
FIGHTING = 6                # EnergyType.FIGHTING (cg/api.py)
FIGHTING_ENERGY = 6         # Basic {F} Energy (SVE 6). Card id and EnergyType coincide by
                            # COINCIDENCE in the data — the read resolves the type through the
                            # Provider, never from the card id.


def _deny_value(setback_damage: float, turns: int) -> float:
    """The armed keep price of a deny slot: the disruption card tier, scaled by the body's relevance,
    halved once per turn the body is still short of attacking.

    ``setback_damage`` is spelled out from CARD FACTS at each call site rather than read back off the
    pilot, so these tests pin the FORMULA instead of restating whatever the pilot computed."""
    return TAG_TIER["gust"] * (setback_damage / _DENY_RELEVANCE_K) / (2.0 ** turns)


def _setup(hand_ids, *, opp_active=None, opp_bench=(), minc=1):
    """A forced Discard over ``hand_ids`` against a visible opponent board — the
    `test_discard_keep_rows` fixture shape plus the opponent side the deny leg reads. The Riolu →
    Mega Lucario ex forward line (single hop — rulebook Appendix 1) carries real attack records so
    the deny read prices strips: Riolu Accelerating Stab {F}=30; Mega Lucario ex Aura Jab {F}=130 /
    Mega Brave {F}{F}=270 (verified, data/EN_Card_Data.csv).

    ``energyTypes`` on each attack record and a real Basic {F} Energy card in the Provider are what
    the ARMED read needs and the retired magnitude oracle did not: relevance is a function of an
    Energy's TYPE against a cost's typed slots, so an untyped placeholder scores 0 everywhere. My
    own Active is present for the same reason — `_opponent_target_rows` builds the deny rows off
    differences of `turns_to_ko_me`, and returns nothing at all when my Active spot is empty."""
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
    """`_opp_turns_to_ready`: max of the energy leg (the LINE's biggest-attack cost — max
    `maxDamageCost` over current + forward forms — minus attached, at 1 attach/turn) and the
    forward-hop leg (`evolvesFrom` name-chain depth, one evolve/turn). A banked Riolu (1 Energy,
    one hop to Mega Lucario ex whose Mega Brave costs 2) is ONE turn out on both legs; a powered
    Mega Lucario ex is ready NOW; an unknown body reads None — fail-closed, no deny slot."""
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
    """The graded Hammer, wired at the CURRENCY ruling: a banked opponent Riolu (1 Energy toward
    Mega Lucario ex) opens ONE deny slot, priced in the ONE currency off the disruption CARD-tier
    (`TAG_TIER["gust"]` = 10) and graded by turns-to-ready (1 turn out → halved, `needs.deny_slot`).
    Never the play-side damage swing.

    **The tier is now the CEILING, not the value (ADR-0080 / Issue #187).** Armed, it is scaled by
    the body's relevance before the grade: that Riolu's lone {F} is banked toward Mega Brave
    ({F}{F}, 270) — "Evolving keeps attached cards", rules.md:98 — credited at the mandated
    `_DENIAL_FORWARD` discount because the payoff is a turn away and contingent, so the setback is
    135 of a 350 normalizer. 10 x (135/350) / 2¹ ≈ 1.93. The ADR-0062 oracle that used to supply
    the bare bite GATE here is deleted (Issue #228); relevance > 0 subsumes it.

    ONLY the deny-supplying rows (energy_denial Hammer, gust Boss's) are eligible, via the
    `needs.SUPPLIES` net."""
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
    """Every unknown reads as NO slot (erring toward the shipped hedge): an unknown-stats body, a
    surplus-Energy body (the ADR-0062 whiff — stripping denies 0), an absent opponent read, and a
    hand with no deny-capable row each emit nothing.

    The surplus case is the one that changed CHARACTER rather than outcome: it used to be the
    ADR-0062 oracle pricing the strip at 0 and the gate declining, and it is now the relevance read
    reaching 0 STRUCTURALLY — a Mega Lucario ex on 3 {F} is surplus in the typed slot of both its
    attacks and over the total cost of both, so no strip puts either further out of reach."""
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
    """The `active_can_ko` drop, consumed intact: with my Active able to KO theirs the doomed Active
    denies nothing and emits NO slot, while every biting body still opens a slot graded by its OWN
    turns-to-ready — the ready Mega Lucario ex Active at the full band (2⁰), the banked bench Riolu
    one turn out at half (2¹). Bench vs Active is a TIMING grade, not a fixed weight: the
    damage-model `_DENIAL_BENCH` discount was retired from the keep price and Issue #228 deleted it.

    Each slot's ceiling is the card tier scaled by that body's own relevance (ADR-0080): the Active
    Mega Lucario ex sits on exactly the {F}{F} Mega Brave needs, so the strip puts its full 270 out
    of reach; the bench Riolu's lone {F} is banked one evolution away, so it takes the
    `_DENIAL_FORWARD` discount on the same 270. Nothing in either figure is an AREA term — the
    deadlines asserted below are where bench-vs-Active shows up, and they come from each body's own
    turns-to-ready."""
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
    """The currency ruling on a REAL recorded board (82867148-48, mega_starmie): the held Boss's
    Orders (gust-tagged) never towers over its own general worth (4.5), whether priced through the
    pre-ADR-0076 `deny` route (a card-tier value graded down for distance) or — the armed default
    now — its own `gust_target` slot (the real per-body marginal, ADR-0076): either way the
    DECIDED pick stays unmoved (the discard corpus stays 12/12; `keep_v2` is unchanged at 4.5,
    its general floor). Under the pre-ruling damage-denominated value the same board priced the
    strip at 35/4 ≈ 8.8 and lifted the Boss's above everything — the exact over-pricing the
    original ruling retired, and the ADR-0076 migration does not reopen.

    **The slot is WORTH-denominated as of Issue #313 item 2g**, so the number below is a band
    fraction (`10.0 x prize_equivalents/3.9`) rather than the raw prize-equivalent it used to be.

    **ADR-TEMP-398 moved this frame's number, and the old prose explaining WHY it was chosen no
    longer describes it.** It read: *"the only gustable body is a 1-prize Dreepy whose removal buys
    no survival turns — the MODAL corpus target"*, held up as the "not everywhere" half of the
    denomination fix. The survival half of that is still true. The prize half is not: Dreepy is two
    hops from **Dragapult ex**, so its LINE is worth 2 where its body is worth 1, and
    `needs.line_prize_advance` reads `1 + (2−1) x halve(2)` = **1.25**. The frame is therefore no
    longer a pure "nothing to see" board — it is a mild lift, which is exactly what a two-hop line
    to a 2-prize ex should earn.

    What the frame actually pins is unchanged, and survives the move: the slot still prices UNDER
    the card's own general floor (3.21 against 4.5), so the held Boss's still never towers over its
    own general worth and the decided pick still moves nothing. That claim is asserted below against
    the floor directly, so it cannot silently become vacuous the next time the marginal moves."""
    # THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089). The inline raw walk
    # this replaced `pytest.skip`ped when the frame was absent — a skip on a test that names a
    # literal frame it asserts real behaviour about is a green nobody can notice, so the helper
    # RAISES instead.
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
    # EXACT, so the marginal's formula is pinned rather than merely bounded (the original assertion
    # here pinned deny's `10 / 2^t` grade the same way; a loose inequality would let the value drift
    # anywhere below the floor unnoticed). Their bench holds one gustable body, a 1-prize Dreepy
    # whose removal buys 0 survival turns — so the survival leg is `phase x 0` = 0 and the whole
    # marginal is `prize_advance`. Since ADR-TEMP-398 that is the LINE's prize: Dreepy is two hops
    # from Dragapult ex (2 prizes), so `1 + (2-1) x halve(2)` = 1.25, denominated into Worth by
    # `currency.target_value_to_worth` at the band fraction 1.25/3.9. It read 1.0 while
    # `prize_advance` was the body's own prize.
    assert len(gust_target) == 1
    assert pilot.combat.forward_line_prize(DREEPY) == (2, 2), (
        "the premise of the number below — a two-hop line to a 2-prize ex, not a dead end")
    assert gust_target[0].value == pytest.approx(currency.target_value_to_worth(1.25))
    assert gust_target[0].value < 4.5                        # ...and so below the card's own floor
    # `keep_v2` used to be read off `Decision.discard_shadow`, deleted with the other three by
    # Issue #261 item 2h. The number was never the shadow's — it is the decider's own keep, so it is
    # read from the assignment that decides.
    keeps, _pick = pilot._needs_v2(rec.obs, board, rows, rec.obs["select"]["maxCount"])
    boss = next(k for r, k in zip(rows, keeps) if r["cid"] == BOSS)
    assert boss == pytest.approx(4.5)                        # its general floor — the strip is below it
    assert pilot.explain(rec.obs).chosen == _pick            # ...and the DECIDED pick is unmoved
