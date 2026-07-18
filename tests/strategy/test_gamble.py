"""Tier 2 — Gamble Lines (ADR-0039): closed-form expectimax over Outcome Classes.

The canonical decision (docs/architecture/tier-2-chance-ev.md): Mega Starmie ex Active with no
Energy, hand = Lillie's Determination + Ignition Energy, opponent Water-weak. The banked line
(attach Ignition → Nebula ●●● 210, Weakness ignored) is safe; refreshing FIRST gambles the hand
for a {W} Basic → Jetting Blow {W} at 240 with Weakness — a KO the held hand cannot reach. The
gamble rung prices that draw with EXACT tracker-anchored hypergeometrics and commits exactly when
the EV beats the deterministic baseline.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


def _deck(agent="mega_starmie"):
    p = REPO / "src" / "agents" / agent / "deck.csv"
    return [int(x) for x in p.read_text(encoding="utf-8").splitlines()[:60] if x.strip()]


def _gamble_obs(opp_hp=230, with_prizes=True):
    """The canonical board: my Mega Starmie ex (1031, 0 Energy) vs a Water-weak Cinderace (666) at
    ``opp_hp``; hand = Lillie's Determination (1227) + Ignition Energy (17); prizes anchored so the
    tracker's exact deck counts exist (own_prizes = the first five deck cards NOT needed by the
    test's math)."""
    deck = _deck()
    hand_ids = [1227, 17]
    prize_ids = [cid for cid in deck if cid not in (1227, 17)][:5]
    seen = list(hand_ids) + [1031]
    own_prizes: dict = {}
    for cid in prize_ids:
        own_prizes[cid] = own_prizes.get(cid, 0) + 1
    me = {"active": [{"id": 1031, "hp": 330, "energies": []}],
          "bench": [], "discard": [],
          "hand": [{"id": c} for c in hand_ids],
          "prize": [None] * 5}
    opp = {"active": [{"id": 666, "hp": opp_hp, "energies": []}],
           "bench": [{"id": 666, "hp": 210}],   # a replacement body: a KO here is NOT the match win,
           "hand": [], "prize": [None] * 6, "discard": []}   # so the win rung passes to the gamble
    obs = {"current": {"yourIndex": 0, "turn": 6, "players": [me, opp],
                       "energyAttached": False},
           "select": {"context": 0, "maxCount": 1, "minCount": 1,
                      "option": [{"type": 13 and 6, "index": 0},   # placeholder replaced below
                                 ]}}
    from common.strategy.context import _ATTACH, _PLAY
    obs["select"]["option"] = [
        {"type": _PLAY, "index": 0},                                   # play Lillie's Determination
        {"type": _ATTACH, "area": 2, "index": 1,                       # the Energy card in hand …
         "inPlayArea": 4, "inPlayIndex": 0},                           # … attached onto my Active
    ]
    if with_prizes:
        obs["own_prizes"] = own_prizes
    _ = seen
    return obs


@pytest.mark.req("REQ-GAMBLE-0001")
def test_the_lillies_gamble_commits_when_ev_beats_the_banked_line():
    """opp at 230: Nebula (210, after banking the Ignition) cannot KO, Jetting (120×2 Weakness =
    240) can — one {W} Basic short. The deck is full of Water Energy, so the 6-draw's hit odds are
    high and the gamble EV (P × KO value) dwarfs the 210 chip: the planner commits the refresh
    FIRST and the trace says why."""
    pilot = _shipped_pilot()
    obs = _gamble_obs(opp_hp=230)
    decision = pilot.explain(obs)
    assert decision.planned is not None and decision.planned.goal == "gamble"
    assert decision.chosen == [0]                        # Lillie's first — the gamble, not the bank
    assert "gamble:" in decision.planned.rationale and "KO" in decision.planned.rationale
    # The full working rides the Decision (sparse `gamble` telemetry, ADR-0019): classes with the
    # SOUGHT out-card ids, per-option p·EV rows, the det baseline, and the committed best.
    tr = decision.gamble
    assert tr is not None and tr["considered"] is True and tr["best"] is not None
    assert tr["classes"] and all(c["sought"] and c["copies"] > 0 for c in tr["classes"])
    assert tr["evals"] and all(0.0 <= e["p"] <= 1.0 for e in tr["evals"])
    from common import telemetry
    rec = telemetry.to_record(decision)
    assert rec["gamble"]["considered"] is True           # the wire record carries it to stderr


@pytest.mark.req("REQ-GAMBLE-0002")
def test_the_gamble_stands_down_when_a_deterministic_ko_exists():
    """opp at 200: the banked Ignition→Nebula already KOs (210 ≥ 200) — a KO_SCORE trace is on the
    tuned menu, so the gamble rung never fires (never gamble past a sure thing)."""
    pilot = _shipped_pilot()
    obs = _gamble_obs(opp_hp=200)
    decision = pilot.explain(obs)
    assert decision.planned is None or decision.planned.goal != "gamble"


@pytest.mark.req("REQ-GAMBLE-0003")
def test_the_gamble_prices_pre_anchor_and_stands_down_when_switched_off():
    """WP2: pre-anchor (no own_prizes → no exact counts) the gamble no longer stands down — the
    decklist is fully known, only the prize split of the unseen copies is random, so it PRICES with
    the prize-split-weighted window sum (`anchored: False`, `prizes_hidden` set) instead of the old
    modeling-gap zero. The {W}-flush deck still clears the bar. Kill-switch off → silent stand-down."""
    pilot = _shipped_pilot()
    decision = pilot.explain(_gamble_obs(opp_hp=230, with_prizes=False))
    tr = decision.gamble
    assert tr is not None and tr["considered"] is True     # it PRICED, it did not stand down
    assert tr["anchored"] is False and tr["prizes_hidden"] == 5
    assert tr["classes"] and all(0.0 <= e["p"] <= 1.0 for e in tr["evals"])
    assert decision.planned is not None and decision.planned.goal == "gamble"   # and clears the bar
    pilot2 = _shipped_pilot()
    pilot2.gamble_lines = False
    pilot2._turn_plan = None
    decision2 = pilot2.explain(_gamble_obs(opp_hp=230))
    assert decision2.planned is None or decision2.planned.goal != "gamble"
    if decision2.planned is None:
        assert decision2.gamble == {"considered": False, "why": "feature off (gamble_lines)"}


@pytest.mark.req("REQ-GAMBLE-0005")
def test_coin_attacks_rank_by_their_mean_when_race_pricing_is_on():
    """A coin/conditional CHIP attack (bounds 0–100) ranks by its mean (50) instead of the exact
    read — honest EV for ranking only; with the switch off, the legacy exact price stands. The KO
    branch and every sound path (Lethal floor / Incoming ceiling) are untouched by construction."""
    from common.pilot import Board
    pilot = _shipped_pilot()
    obs = _gamble_obs(opp_hp=500)                     # a huge wall: nothing KOs, chip branch only
    orig = pilot.predicted_damage

    def fake(attacker_id, attack_id, defender, *, bound="exact", context=None):
        if attack_id == 9999:
            return {"min": 0.0, "max": 100.0}.get(bound, 100.0)
        return orig(attacker_id, attack_id, defender, bound=bound, context=context)

    pilot.predicted_damage = fake
    try:
        board = Board(my_active_id=1031, active_can_ko=False)
        option = {"type": 13, "attackId": 9999}
        priced = pilot._tactical(obs, board, option)
        pilot.objectives_race = False
        legacy = pilot._tactical(obs, board, option)
        pilot.objectives_race = True
    finally:
        pilot.predicted_damage = orig
    assert priced == pytest.approx(50.0)              # the mean — variance priced honestly
    assert legacy == pytest.approx(100.0)             # the legacy exact read, switch off


@pytest.mark.req("REQ-GAMBLE-0004")
def test_draw_hit_probability_is_exact_and_fail_closed():
    """1 − C(pool−k, n)/C(pool, n) exactly; clamps overdraws; bad input → 0.0 (an ENDORSER must
    fail closed — contrast p_contains' 1.0, which guards a suppressor)."""
    from math import comb
    from common.deck_odds import draw_hit_probability
    assert draw_hit_probability(10, 40, 6) == pytest.approx(1 - comb(30, 6) / comb(40, 6))
    assert draw_hit_probability(1, 1, 1) == 1.0
    assert draw_hit_probability(3, 10, 20) == 1.0        # overdraw clamps to the pool → must hit
    assert draw_hit_probability(0, 40, 6) == 0.0
    assert draw_hit_probability("x", 40, 6) == 0.0


@pytest.mark.req("REQ-GAMBLE-0006")
def test_recovery_class_counts_the_held_burst_energy_copies():
    """The recovery class enabler: `_gamble_burst_copies` returns the pool-wide copies (deck +
    returned hand) of a held `discard_eot` burst Energy — the miss branch that redraws it re-banks
    the deterministic line. Zero when no such burst is held."""
    pilot = _shipped_pilot()
    stat = pilot.stats.get(1031)                          # Mega Starmie ex
    hand = [{"id": 17}]                                   # one Ignition (discard_eot) in hand
    counts = {17: 3}                                      # three more in the deck
    assert pilot._gamble_burst_copies(counts, hand, stat) == 4   # 3 deck + 1 returned hand copy
    assert pilot._gamble_burst_copies({}, [{"id": 999}], stat) == 0   # nothing discard_eot held


@pytest.mark.req("REQ-GAMBLE-0007")
def test_wp1_fetch_reaches_slot_predicate():
    """WP1: the interim fetch-closure predicate `_fetch_reaches_slot` — an Item out reaches the
    missing slot only when its type-lock is compatible AND its target is still in the source zone.
    Fighting Gong (deck search, {F}-locked) is the canonical trap: its generic `tutor_energy` tag
    can't see the {F}-lock, so it is a {F} out only, never a {W} out."""
    ml = _shipped_pilot("mega_lucario")
    F, W = 6, 3
    deck = {F: 2, 1142: 4}                                # Fighting basics + Fighting Gong in the deck
    # Fighting Gong (1142) = ("deck", 6): reaches a {F} slot / a colourless slot; NOT a {W} slot.
    assert ml._fetch_reaches_slot(F, ("deck", F), deck, set()) is True
    assert ml._fetch_reaches_slot(None, ("deck", F), deck, set()) is True   # any Basic fills colourless
    assert ml._fetch_reaches_slot(W, ("deck", F), deck, set()) is False     # {F}-locked ≠ a {W} slot
    assert ml._fetch_reaches_slot(F, ("deck", F), {1142: 4}, set()) is False   # no {F} Basic left in deck
    # Recycle (discard zone): reaches iff a matching Basic sits in the VISIBLE discard, no prize split.
    ms = _shipped_pilot("mega_starmie")
    assert ms._fetch_reaches_slot(W, ("discard", None), {}, {W}) is True
    assert ms._fetch_reaches_slot(W, ("discard", None), {}, set()) is False


@pytest.mark.req("REQ-GAMBLE-0007")
def test_wp1_fetch_items_join_the_gamble_ko_class_outs():
    """WP1: a drawable fetch Item whose target is reachable is a closure out — its deck copies join
    the class's `copies`/`sought`. The recycle branch (Night Stretcher, a matching Basic ONLY in the
    discard) makes a class EXIST that the literal-energy-only reading could not (deck has no matching
    Basic left) — the deck-closure ∪ discard-closure the spec calls for. A held tutor voids the class."""
    from common.pilot import Board
    # (a) deck-search closure: Fighting Gong copies added to a Fighting slot's outs.
    ml = _shipped_pilot("mega_lucario")
    stat = ml.stats.get(673)                              # Makuhita: attack 977 = {F}{F}, one short at 1
    board = Board(my_active_id=673, my_active_energy=1)
    ma = {"id": 673, "hp": 110, "energies": [6]}
    opp = {"id": 666, "hp": 30, "energies": []}
    classes = ml._gamble_ko_classes(board, stat, ma, opp, 30, {6: 5, 1142: 4}, [{"id": 1227}], set())
    assert classes and classes[0][3] == [6, 1142]        # sought = literal {F} Basic (6) ∪ Fighting Gong
    assert classes[0][0] == 9                             # 5 Basics + 4 Gong copies in the pool
    # Fighting Gong with NO {F} Basic left in deck cannot fetch anything → not an out, no class.
    assert ml._gamble_ko_classes(board, stat, ma, opp, 30, {1142: 4}, [{"id": 1227}], set()) == []

    # (b) recycle closure: Night Stretcher makes a class the literal reading can't (Basic only in discard).
    ms = _shipped_pilot("mega_starmie")
    st = ms.stats.get(1031)                               # Mega Starmie ex: attack 1487 = {W}, one short at 0
    b = Board(my_active_id=1031, my_active_energy=0)
    msa = {"id": 1031, "hp": 330, "energies": []}
    low = {"id": 666, "hp": 40, "energies": []}
    recycle = ms._gamble_ko_classes(b, st, msa, low, 40, {1097: 2}, [{"id": 1227}], {3})
    assert recycle and recycle[0][3] == [1097] and recycle[0][0] == 2   # the class exists VIA the recycler
    assert ms._gamble_ko_classes(b, st, msa, low, 40, {1097: 2}, [{"id": 1227}], set()) == []  # empty discard
    # A held Night Stretcher + a matching Basic in discard is a DETERMINISTIC tutor line → class voided.
    assert ms._gamble_ko_classes(b, st, msa, low, 40, {1097: 2}, [{"id": 1097}], {3}) == []


@pytest.mark.req("REQ-GAMBLE-0008")
def test_wp2_prize_split_hit_is_the_exact_closed_form():
    """WP2: `_prize_split_hit(u, deck, prizes, pool, n)` = Σ_j C(deck,j)C(prizes,u−j)/C(deck+prizes,u)
    × window(j). Degenerates to the plain window draw with no hidden prizes; discounts BELOW it once
    copies can be prized; fails closed on garbage (an endorser)."""
    from math import comb
    from common.deck_odds import draw_hit_probability
    pilot = _shipped_pilot()
    # No hidden prizes → every unseen copy is in the deck → identical to the plain window draw.
    assert pilot._prize_split_hit(3, 40, 0, 40, 6) == pytest.approx(draw_hit_probability(3, 40, 6))
    # With hidden prizes the copies may be prized → strictly BELOW the all-in-deck probability.
    split = pilot._prize_split_hit(3, 40, 6, 40, 6)
    assert 0.0 < split < draw_hit_probability(3, 40, 6)
    # Exact against the hand-rolled sum (u=2, deck=10, prizes=4, pool=10, n=3).
    u, d, k, pool, n = 2, 10, 4, 10, 3
    expect = sum(comb(d, j) * comb(k, u - j) / comb(d + k, u) * draw_hit_probability(j, pool, n)
                 for j in range(max(0, u - k), min(u, d) + 1))
    assert pilot._prize_split_hit(u, d, k, pool, n) == pytest.approx(expect)
    assert pilot._prize_split_hit(0, 40, 6, 40, 6) == 0.0      # no copies → never hits
    assert pilot._prize_split_hit("x", 40, 6, 40, 6) == 0.0    # garbage → fail closed


@pytest.mark.req("REQ-GAMBLE-0009")
def test_wp5_evolution_ko_gamble_class_prices_drawing_the_evolution():
    """WP5: the evolution-KO class — a Staryu Active (in play since last turn) that, evolved to Mega
    Starmie ex, KOs with its carried Energy + one attach. The gamble to DRAW the evolution is priced,
    its outs = the evolution's copies ∪ the Item Pokémon-tutor closure (Ultra Ball / Mega Signal —
    Supporter tutors are slot-dead post-refresh). Voided when the evolution is in hand (deterministic
    evolve-KO), and when the Active was placed THIS turn (rules.md §4: can't evolve a new-in-play body)."""
    from common.pilot import Board
    ms = _shipped_pilot("mega_starmie")
    ma = {"id": 1030, "hp": 70, "energies": [3, 3], "appearThisTurn": False}   # Staryu, 2 {W}, eligible
    opp = {"id": 666, "hp": 240, "energies": []}
    board = Board(my_active_id=1030, my_active_energy=2)
    counts = {1031: 3, 1121: 4, 1145: 2}                  # Mega Starmie ex + Ultra Ball + Mega Signal
    classes = ms._gamble_evolution_ko_classes({"current": {}}, board, ma, opp, counts, [{"id": 1227}])
    assert classes and classes[0][3] == [1031, 1121, 1145]   # evolution ∪ Item Pokémon-tutor closure
    assert classes[0][0] == 9 and "Mega Starmie ex" in classes[0][2]
    # Placed this turn → ineligible to evolve; evolution in hand → deterministic line, both void it.
    placed = {**ma, "appearThisTurn": True}
    assert ms._gamble_evolution_ko_classes({"current": {}}, board, placed, opp, counts, [{"id": 1227}]) == []
    assert ms._gamble_evolution_ko_classes({"current": {}}, board, ma, opp, counts, [{"id": 1031}]) == []
