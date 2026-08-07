"""Tier 2 — Gamble Lines (ADR-0039): closed-form expectimax over Outcome Classes.

The canonical decision (docs/architecture/tiers.md): Mega Starmie ex Active with no
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
    """Mega Starmie ex (1031, 0 Energy) vs a Water-weak Cinderace (666) at ``opp_hp``; hand =
    Lillie's (1227) + Ignition (17); prizes anchored so the tracker's exact deck counts exist."""
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
    """opp at 230: Nebula (210, banking the Ignition) cannot KO; Jetting (120x2 Weakness = 240) can,
    one {W} Basic short. The {W}-flush deck makes the 6-draw's EV dwarf the 210 chip."""
    pilot = _shipped_pilot()
    obs = _gamble_obs(opp_hp=230)
    decision = pilot.explain(obs)
    assert decision.planned is not None and decision.planned.goal == "gamble"
    assert decision.chosen == [0]                        # Lillie's first — the gamble, not the bank
    assert "gamble:" in decision.planned.rationale and "KO" in decision.planned.rationale
    # the full working rides the Decision as sparse `gamble` telemetry (ADR-0019)
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
    """Pre-anchor the decklist is still fully known — only the prize SPLIT of unseen copies is
    random — so it prices with the prize-split-weighted window sum rather than standing down."""
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
    """Honest EV for RANKING only: the KO branch and every sound path (Lethal floor / Incoming
    ceiling) are untouched by construction."""
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
    """Pool-wide copies (deck + RETURNED hand) of a held `discard_eot` burst: the miss branch that
    redraws it re-banks the deterministic line."""
    pilot = _shipped_pilot()
    stat = pilot.stats.get(1031)                          # Mega Starmie ex
    hand = [{"id": 17}]                                   # one Ignition (discard_eot) in hand
    counts = {17: 3}                                      # three more in the deck
    assert pilot._gamble_burst_copies(counts, hand, stat) == 4   # 3 deck + 1 returned hand copy
    assert pilot._gamble_burst_copies({}, [{"id": 999}], stat) == 0   # nothing discard_eot held


@pytest.mark.req("REQ-GAMBLE-0007")
def test_fetch_predicates_live_in_the_card_representation_not_text():
    """The tutor/recycle predicate lives in `card_effects.json` FETCH clauses, so no card text is
    parsed. Assertions read FIELDS, not whole dicts, so a new declared field cannot fail them."""
    from common.effects import CardEffects
    eff = CardEffects.load()

    def leg(clauses, **fields):
        """The clause carrying these predicate fields — subset, not dict equality."""
        return next((c for c in clauses if all(c.get(k) == v for k, v in fields.items())), None)

    gong = eff.clauses(1142)
    assert leg(gong, kind="fetch", target="basic_energy", zone="deck", energy_type=6)
    assert leg(gong, kind="fetch", target="basic_pokemon", zone="deck", energy_type=6)
    # the plain any-Basic searchers, the discard recyclers, and the no-Rule-Box / mega Pokémon tutors
    assert {"kind": "fetch", "target": "basic_energy", "zone": "deck"} in eff.clauses(1119)
    assert ({"kind": "fetch", "target": "basic_energy", "zone": "discard", "amount": 2}
            in eff.clauses(1118))
    assert leg(eff.clauses(1097), kind="fetch", target="basic_energy", zone="discard")
    # the RELATION, pinned beside the predicates: both are read off the same legs
    from common.fetch_closure import reveal_legs
    for cid in (1142, 1097):
        assert reveal_legs(eff.clauses(cid)).relation == "union", cid
        assert reveal_legs(eff.clauses(cid)).cap == 1, cid
    assert eff.clauses(1152)[0].get("no_rule_box") is True           # Poké Pad
    assert eff.clauses(1145)[0].get("target") == "mega"              # Mega Signal


@pytest.mark.req("REQ-GAMBLE-0007")
def test_wp1_fetch_reaches_slot_reads_the_clause_representation():
    """Fighting Gong (1142) is the trap: its `energy_type: 6` clause makes it a {F} out only, which
    the generic `tutor_energy` tag cannot carry."""
    ml = _shipped_pilot("mega_lucario")
    F, W = 6, 3
    deck = {F: 2, 1142: 4}                                # Fighting basics + Fighting Gong in the deck
    assert ml.effects.clauses(1142)                       # the clause tier carries the predicate
    assert ml._fetch_reaches_slot(F, 1142, deck, set()) is True
    assert ml._fetch_reaches_slot(None, 1142, deck, set()) is True    # any Basic fills a colourless slot
    assert ml._fetch_reaches_slot(W, 1142, deck, set()) is False      # {F}-locked ≠ a {W} slot
    assert ml._fetch_reaches_slot(F, 1142, {1142: 4}, set()) is False   # no {F} Basic left in deck
    # Recycle (discard-zone clause): reaches iff a matching Basic sits in the VISIBLE discard.
    ms = _shipped_pilot("mega_starmie")
    assert ms._fetch_reaches_slot(W, 1097, {1097: 2}, {W}) is True    # Night Stretcher, {W} in discard
    assert ms._fetch_reaches_slot(W, 1097, {1097: 2}, set()) is False  # empty discard → no recycle
    assert ms._fetch_reaches_slot(W, 3, {3: 4}, set()) is False       # a Basic Energy is not a fetcher


@pytest.mark.req("REQ-GAMBLE-0007")
def test_wp1_fetch_items_join_the_gamble_ko_class_outs():
    """A drawable fetch Item whose target is reachable is a closure out (deck-closure ∪
    discard-closure); a HELD tutor is a deterministic line, so it voids the class."""
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
    """`_prize_split_hit(u, deck, prizes, pool, n)` = Σ_j C(deck,j)C(prizes,u−j)/C(deck+prizes,u) ×
    window(j)."""
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
    """Outs = the evolution's copies ∪ the ITEM Pokémon-tutor closure (Supporter tutors are slot-dead
    post-refresh). A body placed THIS turn cannot evolve (rules.md §4), so it voids the class."""
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
    # Poké Pad's `no_rule_box` clause EXCLUDES a Rule-Box Mega ex — a fact the `tutor_pokemon` tag
    # cannot carry — while Ultra Ball and Mega Signal include it.
    ml = _shipped_pilot("mega_lucario")
    megalu = next(cid for cid in set(ml.deck) if (s := ml.stats.get(cid)) and getattr(s, "megaEx", False))
    assert ml._fetch_reaches_pokemon(megalu, 1152, {megalu: 1, 1152: 4}) is False   # Poké Pad: no Rule Box
    assert ml._fetch_reaches_pokemon(megalu, 1121, {megalu: 1, 1121: 4}) is True    # Ultra Ball: any Pokémon


@pytest.mark.req("REQ-GAMBLE-0010")
def test_supporter_tutors_reach_only_what_their_clauses_can_deliver():
    """A conditioned accel (Rosa's prize-behind gate) fails closed; Petrel is the 2-hop, live only
    while an energy-fetch ITEM with a reachable target is still in deck."""
    ml = _shipped_pilot("mega_lucario")
    F, W = 6, 3
    assert ml._supporter_energy_tutor_reaches(1219, F, {F: 5, 1142: 4, 1219: 1}, set()) is True
    assert ml._supporter_energy_tutor_reaches(1219, F, {F: 5, 1219: 1}, set()) is False   # no fetch Item
    assert ml._supporter_energy_tutor_reaches(1219, W, {F: 5, 1142: 4, 1219: 1}, set()) is False  # {F}-lock
    ms = _shipped_pilot("mega_starmie")
    assert ms._supporter_energy_tutor_reaches(1225, W, {W: 5, 1225: 2}, set()) is True    # Hilda
    assert ms._supporter_energy_tutor_reaches(1225, W, {1225: 2}, set()) is False         # deck dry
    dx = _shipped_pilot("dragapult_ex")
    assert dx._supporter_energy_tutor_reaches(1198, None, {2: 4, 1198: 3}, set()) is True   # Crispin
    assert dx._supporter_energy_tutor_reaches(1240, None, {2: 4, 1240: 1}, set()) is False  # Rosa: gated
    # Evolution side: Hilda (evolution fetch) and Salvatore (rush-evolve) both deliver Mega Starmie ex.
    assert ms._supporter_evolution_tutor_reaches(1225, 1031, {1031: 3, 1225: 2}) is True
    assert ms._supporter_evolution_tutor_reaches(1189, 1031, {1031: 3, 1189: 2}) is True
    assert ms._supporter_evolution_tutor_reaches(1189, 1031, {1189: 2}) is False          # target gone
    # A HELD Supporter tutor voids the class while the slot is live (play it now — the deterministic
    # line); with the slot already spent it is dead paper, so the gamble class stands.
    from common.pilot import Board
    st = ms.stats.get(1031)
    msa = {"id": 1031, "hp": 330, "energies": []}
    low = {"id": 666, "hp": 40, "energies": []}
    live = Board(my_active_id=1031, my_active_energy=0)
    spent = Board(my_active_id=1031, my_active_energy=0, supporter_played=True)
    assert ms._gamble_ko_classes(live, st, msa, low, 40, {W: 5, 1225: 2}, [{"id": 1225}], set()) == []
    assert ms._gamble_ko_classes(spent, st, msa, low, 40, {W: 5, 1225: 2}, [{"id": 1225}], set()) != []


@pytest.mark.req("REQ-GAMBLE-0010")
def test_supporter_outs_count_only_when_the_refresh_is_an_item():
    """A Supporter refresh spends the one-per-turn slot, so a drawn Supporter tutor is dead in ITS
    window: the supplement applies only to the ITEM option, and not even then once the slot is spent."""
    from math import isclose
    from common.pilot import Board
    from common.deck_odds import draw_hit_probability
    from common.strategy.doctrines.doctrine_shuffle_refresh import _draw_branches
    ml = _shipped_pilot("mega_lucario")
    counts = {6: 5, 1142: 4, 1219: 1}                     # {F} Basics + Fighting Gong + Petrel in deck
    hand = [1080, 1227]                                   # Unfair Stamp (Item) + Lillie's (Supporter)
    me = {"active": [{"id": 673, "hp": 110, "energies": [6]}], "bench": [],
          "hand": [{"id": c} for c in hand], "discard": [], "prize": [None] * 3}
    opp = {"active": [{"id": 666, "hp": 30, "energies": []}], "bench": [], "prize": [None] * 3}
    obs = {"current": {"yourIndex": 0, "turn": 6, "players": [me, opp], "energyAttached": False}}
    from common.strategy.context import _PLAY
    select = {"option": [{"type": _PLAY, "area": 2, "index": 0},
                         {"type": _PLAY, "area": 2, "index": 1}]}
    obs["select"] = select
    board = Board(turn=6, my_active_id=673, my_active_energy=1, deck_known_counts=counts,
                  my_prizes_remaining=3, opp_prizes_remaining=3)
    ml._best_gamble_line(obs, select, board, select["option"], [])
    tr = ml._gamble_trace
    assert tr["classes"][0]["post_item_copies"] == 1      # the Petrel supplement, carried on the class
    assert tr["classes"][0]["post_item_sought"] == [1219]
    pool = tr["pool"]
    stamp = next(e for e in tr["evals"] if e["cid"] == 1080)
    lillies = next(e for e in tr["evals"] if e["cid"] == 1227)
    b_stamp, b_lil = _draw_branches(1080, board), _draw_branches(1227, board)
    assert stamp["post_item_sup"] == 1                    # supplement applied: 9 literal+Item outs + 1
    assert isclose(stamp["p"], round(sum(draw_hit_probability(10, pool, n) for n in b_stamp)
                                     / len(b_stamp), 3))
    assert "post_item_sup" not in lillies                 # a Supporter refresh spends the slot
    assert isclose(lillies["p"], round(sum(draw_hit_probability(9, pool, n) for n in b_lil)
                                       / len(b_lil), 3))
    # A Supporter already played this turn kills the supplement even for the Item refresh.
    ml._gamble_trace = None
    board2 = Board(turn=6, my_active_id=673, my_active_energy=1, deck_known_counts=counts,
                   my_prizes_remaining=3, opp_prizes_remaining=3, supporter_played=True)
    ml._best_gamble_line(obs, select, board2, select["option"], [])
    stamp2 = next(e for e in ml._gamble_trace["evals"] if e["cid"] == 1080)
    assert "post_item_sup" not in stamp2


@pytest.mark.req("REQ-GAMBLE-0011")
def test_wp4_engine_derivation_is_board_gated():
    """A drawn engine counts only if its ability is unconditional-once-in-play AND an eligible base
    is on board. Depth = Σ min(copies, eligible bases); the window is the MINIMUM usable one."""
    dx = _shipped_pilot("dragapult_ex")
    counts = {120: 3, 66: 1, 5: 4}
    dreepy = {"id": 119, "hp": 70, "energies": [], "appearThisTurn": False}
    me = {"active": [{"id": 112, "hp": 110, "energies": [5]}], "bench": [dreepy]}
    copies, windows, ids = dx._gamble_draw_engines(me, counts, set())
    assert (copies, windows, ids) == (3, (2,), [120])          # 1 eligible Dreepy -> depth 1, Recon window
    two = {**me, "bench": [dreepy, dict(dreepy)]}
    assert dx._gamble_draw_engines(two, counts, set())[1] == (2, 2)   # 2 eligible bases -> depth 2
    placed = {**me, "bench": [{**dreepy, "appearThisTurn": True}]}
    assert dx._gamble_draw_engines(placed, counts, set()) == (0, (), [])   # new-in-play: can't evolve
    assert dx._gamble_draw_engines({**me, "bench": []}, counts, set()) == (0, (), [])   # no base at all
    dun = {"id": 305, "hp": 60, "energies": [], "appearThisTurn": False}
    both = {**me, "bench": [dreepy, dun]}
    copies_b, windows_b, ids_b = dx._gamble_draw_engines(both, counts, set())
    assert copies_b == 4 and ids_b == [66, 120]                # both lines usable
    assert windows_b == (2, 2)                                 # 2 activations, min window (Recon's 2)
    assert dx._gamble_draw_engines(both, counts, {120}) == (1, (3,), [66])   # exclusion drops Drakloak


@pytest.mark.req("REQ-GAMBLE-0011")
def test_wp4_engine_windows_lift_the_anchored_gamble_price():
    """The anchored eval prices with the two-window form (base + the missed-but-drew-engine branch
    over the thinned pool). Pre-anchor stays plain: engines are an anchored-only sharpening."""
    from math import isclose
    from common.pilot import Board
    from common.deck_odds import draw_hit_probability, draw_hit_with_engines
    from common.strategy.doctrines.doctrine_shuffle_refresh import _draw_branches
    from common.strategy.context import _PLAY
    dx = _shipped_pilot("dragapult_ex")
    counts = {5: 4, 120: 2, 119: 1, 9999: 5}                   # outs=4 psychic; engines=2 Drakloak
    dreepy = {"id": 119, "hp": 70, "energies": [], "appearThisTurn": False}
    me = {"active": [{"id": 112, "hp": 110, "energies": [5]}], "bench": [dreepy],
          "hand": [{"id": 1227}], "discard": [], "prize": [None] * 3}
    opp = {"active": [{"id": 666, "hp": 60, "energies": []}], "bench": [], "prize": [None] * 3}
    obs = {"current": {"yourIndex": 0, "turn": 6, "players": [me, opp], "energyAttached": False},
           "select": {"option": [{"type": _PLAY, "area": 2, "index": 0}]}}
    board = Board(turn=6, my_active_id=112, my_active_energy=1, deck_known_counts=counts,
                  my_prizes_remaining=3, opp_prizes_remaining=3)
    dx._best_gamble_line(obs, obs["select"], board, obs["select"]["option"], [])
    tr = dx._gamble_trace
    cls = tr["classes"][0]
    assert cls["engine_copies"] == 2 and cls["engine_windows"] == [2] and cls["engine_ids"] == [120]
    pool, ns = tr["pool"], _draw_branches(1227, board)
    expect = sum(draw_hit_with_engines(4, pool, n, 2, (2,)) for n in ns) / len(ns)
    assert isclose(tr["evals"][0]["p"], round(expect, 3))
    assert expect > sum(draw_hit_probability(4, pool, n) for n in ns) / len(ns)   # a real lift
    # Same board, Dreepy placed THIS turn: no usable engine -> the plain window price.
    dx._gamble_trace = None
    me2 = {**me, "bench": [{**dreepy, "appearThisTurn": True}]}
    obs2 = {**obs, "current": {**obs["current"], "players": [me2, opp]}}
    dx._best_gamble_line(obs2, obs["select"], board, obs["select"]["option"], [])
    tr2 = dx._gamble_trace
    assert "engine_copies" not in tr2["classes"][0]
    plain = sum(draw_hit_probability(4, pool, n) for n in ns) / len(ns)
    assert isclose(tr2["evals"][0]["p"], round(plain, 3))


def test_chain_refresh_lifts_the_window_when_a_drawn_refresh_is_live():
    """A window may miss its outs but draw ANOTHER refresh, whose replay is a fresh full window. The
    chain branch conditions on missing every out, so it adds disjointly."""
    from math import isclose
    from common.pilot import Board
    from common.deck_odds import draw_hit_probability as hitp
    from common.strategy.doctrines.doctrine_shuffle_refresh import _draw_branches
    from common.strategy.refresh import own_draw_count
    from common.strategy.context import _PLAY
    dx = _shipped_pilot("dragapult_ex")
    counts = {5: 4, 1080: 1, 9999: 10}                     # outs = 4 Basic Psychic; 1 Unfair Stamp
    me = {"active": [{"id": 112, "hp": 110, "energies": [5]}], "bench": [],
          "hand": [{"id": 1227}], "discard": [], "prize": [None] * 3}
    opp = {"active": [{"id": 666, "hp": 60, "energies": []}], "bench": [], "prize": [None] * 3}
    obs = {"current": {"yourIndex": 0, "turn": 6, "players": [me, opp], "energyAttached": False},
           "select": {"option": [{"type": _PLAY, "area": 2, "index": 0}]}}
    board = Board(turn=6, my_active_id=112, my_active_energy=1, deck_known_counts=counts,
                  my_prizes_remaining=3, opp_prizes_remaining=3, my_pokemon_koed_last_turn=True)
    dx._best_gamble_line(obs, obs["select"], board, obs["select"]["option"], [])
    tr = dx._gamble_trace
    w = int(own_draw_count(1080, 3, 3))                    # the Stamp's own draw window
    assert tr["evals"][0]["chain_refresh"] == [1, w]
    pool, ns = tr["pool"], _draw_branches(1227, board)
    expect = sum(hitp(4, pool, n)
                 + (hitp(5, pool, n) - hitp(4, pool, n)) * hitp(4, pool - 1, w)
                 for n in ns) / len(ns)
    assert isclose(tr["evals"][0]["p"], round(expect, 3))
    assert expect > sum(hitp(4, pool, n) for n in ns) / len(ns)          # a real lift
    # Same board WITHOUT the KO fact: the drawn Stamp is dead -> plain window, no chain block.
    dx._gamble_trace = None
    board2 = Board(turn=6, my_active_id=112, my_active_energy=1, deck_known_counts=counts,
                   my_prizes_remaining=3, opp_prizes_remaining=3)
    dx._best_gamble_line(obs, obs["select"], board2, obs["select"]["option"], [])
    tr2 = dx._gamble_trace
    assert "chain_refresh" not in tr2["evals"][0]
    plain = sum(hitp(4, pool, n) for n in ns) / len(ns)
    assert isclose(tr2["evals"][0]["p"], round(plain, 3))
    # The SUPPORTER leg: play the Stamp (an Item, slot unspent) with 3 Lillie's in deck — they
    # chain (window = Lillie's own draw); played-as-Supporter above they never did.
    dx._gamble_trace = None
    counts3 = {5: 4, 1227: 3, 9999: 10}
    me3 = {**me, "hand": [{"id": 1080}]}
    obs3 = {**obs, "current": {**obs["current"], "players": [me3, opp]}}
    board3 = Board(turn=6, my_active_id=112, my_active_energy=1, deck_known_counts=counts3,
                   my_prizes_remaining=3, opp_prizes_remaining=3)
    dx._best_gamble_line(obs3, obs3["select"], board3, obs3["select"]["option"], [])
    tr3 = dx._gamble_trace
    w3 = int(own_draw_count(1227, 3, 3))
    assert tr3["evals"][0]["chain_refresh"] == [3, w3]


def _pump_obs(ma, opp):
    return {"current": {"yourIndex": 0, "turn": 6,
                        "players": [{"active": [ma], "bench": [], "hand": [], "discard": []},
                                    {"active": [opp], "bench": [], "discard": []}]}}


@pytest.mark.req("REQ-GAMBLE-0012")
def test_wp5_damage_pump_ko_class():
    """Short of the KO by <= one boost. The gates mirror `_boost_lethal_tactical` exactly (attacker
    type via `energyType`, defender `{ex}`)."""
    from common.pilot import Board
    ml = _shipped_pilot("mega_lucario")
    stat = ml.stats.get(678)                              # Mega Lucario ex, {F}=6, Mega Brave 270 at 2 E
    ma = {"id": 678, "hp": 340, "energies": [6, 6]}
    board = Board(turn=6, my_active_id=678, my_active_energy=2)
    short = {"id": 666, "hp": 290, "energies": []}        # 270 < 290 ≤ 300 → one Power Pro crosses
    obs = _pump_obs(ma, short)
    cls = ml._gamble_pump_ko_classes(obs, board, stat, ma, short, 290, {1141: 4}, [{"id": 1227}])
    assert cls and cls[0][3] == [1141] and cls[0][0] == 4          # Premium Power Pro is the out
    # Too healthy for a single boost (270+30 < 320), an affordable KO already exists (≤270), and the
    # boost already in hand (deterministic play) all yield NO class.
    assert ml._gamble_pump_ko_classes(_pump_obs(ma, {"id": 666, "hp": 320, "energies": []}),
                                      board, stat, ma, {"id": 666, "hp": 320}, 320, {1141: 4},
                                      [{"id": 1227}]) == []
    assert ml._gamble_pump_ko_classes(_pump_obs(ma, {"id": 666, "hp": 260, "energies": []}),
                                      board, stat, ma, {"id": 666, "hp": 260}, 260, {1141: 4},
                                      [{"id": 1227}]) == []
    assert ml._gamble_pump_ko_classes(obs, board, stat, ma, short, 290, {1141: 4},
                                      [{"id": 1141}]) == []
    # Black Belt's (Supporter, +40 vs ex) rides the SUPPLEMENT slot and only vs an ex defender.
    ex_opp = {"id": 678, "hp": 300, "energies": []}      # a Mega ex wall: 270 < 300 ≤ 310 (270+40)
    exc = ml._gamble_pump_ko_classes(_pump_obs(ma, ex_opp), board, stat, ma, ex_opp, 300,
                                     {1211: 4}, [{"id": 1227}])
    assert exc and exc[0][3] == [] and exc[0][4] == (4, [1211])    # Belt's in the post-Item supplement
    non_ex = {"id": 666, "hp": 300, "energies": []}      # Cinderace is not ex → the vsEx gate blocks
    assert ml._gamble_pump_ko_classes(_pump_obs(ma, non_ex), board, stat, ma, non_ex, 300,
                                      {1211: 4}, [{"id": 1227}]) == []


@pytest.mark.req("REQ-GAMBLE-0013")
def test_wp5_gust_ko_class():
    """My Active cannot KO their Active but CAN KO a benched target once dragged up (per-target
    weakness via the shared `_can_ko` oracle); the value is that target's prize."""
    from common.pilot import Board
    ml = _shipped_pilot("mega_lucario")
    ma = {"id": 678, "hp": 340, "energies": [6, 6]}      # Mega Lucario ex, Aura Jab 130 / Mega Brave 270
    board = Board(turn=6, my_active_id=678, my_active_energy=2)
    obs = {"current": {"yourIndex": 0, "players": [{"active": [ma]}, {}]}}
    reachable = {"active": [{"id": 678, "hp": 340, "energies": []}],   # a Mega ex wall (no direct KO)
                 "bench": [{"id": 666, "hp": 60}]}                     # a 60-HP benched target → KOable
    cls = ml._gamble_gust_ko_classes(obs, board, ma, reachable, [{"id": 1227}], {1182: 2})
    assert cls and cls[0][3] == [] and cls[0][4] == (2, [1182])       # Boss's rides the supplement
    assert cls[0][1] > 1000                                            # KO_SCORE + the benched prize
    walls = {"active": [{"id": 678, "hp": 340}], "bench": [{"id": 678, "hp": 340}]}   # nothing KO-able
    assert ml._gamble_gust_ko_classes(obs, board, ma, walls, [{"id": 1227}], {1182: 2}) == []
    assert ml._gamble_gust_ko_classes(obs, board, ma, reachable, [{"id": 1182}], {1182: 2}) == []


@pytest.mark.req("REQ-GAMBLE-0014")
def test_wp5_bench_fill_anti_donk_survival_class():
    """Bench EMPTY + Active doomed = a KO of my only Pokémon ends the game, so the class is valued at
    KO_SCORE scale (a loss averted)."""
    from common.pilot import Board
    ms = _shipped_pilot("mega_starmie")
    ma = {"id": 1031, "hp": 40, "energies": []}
    me = {"active": [ma], "bench": [], "hand": [{"id": 1227}]}
    doomed = Board(active_doomed=True, my_active_id=1031)
    counts = {1030: 4, 1086: 4}                           # Staryu (Basic) + Buddy-Buddy Poffin
    cls = ms._gamble_survival_classes({"current": {}}, doomed, me, counts, [{"id": 1227}])
    assert cls and cls[0][3] == [1030, 1086]              # the Basic AND the bench-fill Item are outs
    assert cls[0][1] >= 1000 and cls[0][4] == (0, [])     # loss-scale value, no Supporter supplement
    # A benchable Basic in hand → bench it (deterministic); bench occupied → no donk; not doomed → safe.
    assert ms._gamble_survival_classes({"current": {}}, doomed, me, counts, [{"id": 1030}]) == []
    occupied = {**me, "bench": [{"id": 1030, "hp": 70}]}
    assert ms._gamble_survival_classes({"current": {}}, doomed, occupied, counts, [{"id": 1227}]) == []
    safe = Board(active_doomed=False, my_active_id=1031)
    assert ms._gamble_survival_classes({"current": {}}, safe, me, counts, [{"id": 1227}]) == []


@pytest.mark.req("REQ-GAMBLE-0014")
def test_wp5_survival_heal_out_lifts_the_doomed_active_above_the_incoming():
    """A full heal is an out only when max HP > the incoming, and only on an Active carrying damage
    to heal."""
    from common.pilot import Board
    ms = _shipped_pilot("mega_starmie")
    ma = {"id": 1031, "hp": 100, "energies": [3]}        # Mega Starmie ex (max 330), 100 HP (damaged)
    me = {"active": [ma], "bench": [], "hand": [{"id": 1227}]}
    obs = {"current": {"yourIndex": 0, "players": [me, {}]}}
    doomed = Board(active_doomed=True, incoming_active_damage=250, my_active_id=1031)
    cls = ms._gamble_survival_classes(obs, doomed, me, {1229: 1}, [{"id": 1227}])
    assert cls and cls[0][4] == (1, [1229])              # Wally's (330 > 250) rides the supplement
    # Incoming ≥ max HP → even a full heal is KO'd; a full-HP Active has no damage to heal.
    big = Board(active_doomed=True, incoming_active_damage=340, my_active_id=1031)
    assert ms._gamble_survival_classes(obs, big, me, {1229: 1}, [{"id": 1227}]) == []
    full = {**me, "active": [{"id": 1031, "hp": 330, "energies": [3]}]}
    obs_full = {"current": {"yourIndex": 0, "players": [full, {}]}}
    assert ms._gamble_survival_classes(obs_full, doomed, full, {1229: 1}, [{"id": 1227}]) == []
    # A held heal that averts is the deterministic play → the class stands down.
    assert ms._gamble_survival_classes(obs, doomed, me, {1229: 1}, [{"id": 1229}]) == []


@pytest.mark.req("REQ-GAMBLE-0015")
def test_wp6_ko_gamble_fires_despite_a_held_line_preevo_via_graded_keep_cost():
    """The protected-hand stand-downs are a graded keep-cost priced into the det baseline, so a
    KO-scale gamble outweighs holding a re-accessible Line pre-evolution."""
    pilot = _shipped_pilot()
    obs = _gamble_obs(opp_hp=230)
    obs["current"]["players"][0]["hand"].append({"id": 1030})   # Staryu — the line pre-evolution
    decision = pilot.explain(obs)
    assert decision.planned is not None and decision.planned.goal == "gamble"   # fires despite the pre-evo
    assert "keep" in decision.planned.rationale                 # the keep-cost is named in the working
    tr = decision.gamble
    assert tr["considered"] is True and any("keep" in e for e in tr["evals"])
