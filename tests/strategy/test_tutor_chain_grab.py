"""Tutor-chain grab value (seam C, docs/plans/seam-tutor-chain-grab-value.md) — spec Round 9 §3:
"a tutor's held value = the closure-reachable value, recursively free."

The acceptance board is the recorded ml 85059103 f9 (CRITICAL): at Meowth ex's Last-Ditch Catch
TO_HAND Supporter grab, the agent took a draw Supporter (Judge, `grab-a-draw-supporter-in-setup`
+10) over Team Rocket's Petrel (0) — but Petrel opens the chain Petrel → Fighting Gong (an Item,
free the same turn) → the Solrock that completes the Solrock↔Lunatone draw engine
(`fetch-the-missing-engine-half` +22). The duplicate Lillie's was ALREADY correctly avoided
(`dont-grab-a-card-already-in-hand`); the gap is chain VALUE, not redundancy.

These tests pin the settled mechanism (the seam doc's grill answers): δ = 0.75 per hop, MAX never a
sum, 2-hop cap, Item-only descent, Supporter-slot fail-closed, hand/deck-empty target exclusion,
and the decay of the chain once its END target is acquired (the `_greedy_grab` invariant).
"""
from __future__ import annotations

import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

PETREL, FIGHTING_GONG, JUDGE, LILLIES = 1219, 1142, 1213, 1227
SOLROCK, MEGA_LUCARIO_EX = 676, 678
POKE_PAD, ULTRA_BALL = 1152, 1121
_FIGHTING = 6


def _record() -> dict:
    """The recorded ml 85059103 f9 correction (the corpus target this seam flips)."""
    for jf in CORR.glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == "85059103" and d.get("decision", {}).get("frame") == 9:
                return d
    raise AssertionError("correction 85059103-9 not found in data/corrections/")


def _pilot():
    """A FRESH pilot per test — the Pilot is stateful across `explain()` calls (the corpus-test
    discipline: the deck tracker accumulates one game's observations)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_lucario")[0]


@pytest.fixture()
def rec():
    return _record()


@pytest.fixture()
def pilot():
    return _pilot()


@pytest.fixture()
def board(pilot, rec):
    return pilot._board(rec["obs"], rec["obs"].get("select"))


@pytest.mark.req("REQ-GEN-0077")
def test_petrel_outranks_the_draw_supporter_at_the_grab(pilot, rec):
    """The acceptance flip: Petrel (the chain opener) is chosen over Judge (+10). The chain rung
    fires on Petrel and stays silent on the draw Supporters (one currency zone: a card rides the
    draw band OR the chain band, never both)."""
    dec = pilot.explain(rec["obs"])
    assert dec.chosen == rec["correct"], (
        f"expected {rec['correct_label']!r}, got {rec['chosen_label'] if dec.chosen == rec['chosen'] else dec.chosen!r}")
    by_card = {}
    for t in dec.options:
        by_card.setdefault(t.card_id, t)
    petrel, judge = by_card[PETREL], by_card[JUDGE]
    assert any(h.id == "grab-the-chain-opener" for h, _ in petrel.fired)
    assert not any(h.id == "grab-the-chain-opener" for h, _ in judge.fired)
    assert petrel.score > judge.score


@pytest.mark.req("REQ-GEN-0077")
def test_chain_value_is_the_discounted_closure_max(pilot, board):
    """chain_value(Petrel) = δ² × grab_value(Solrock) exactly: two hops (Petrel → Fighting Gong →
    Solrock), δ = 0.75 per hop, Solrock's `fetch-the-missing-engine-half` +22 as the end value.
    Pinning the EXACT number also pins the exclusions: the held Mega Lucario ex (grab value 30, in
    hand → excluded) must NOT be the max (0.75² × 30 = 16.875 would be wrong), and MAX not SUM."""
    from common.strategy.doctrines.doctrine_fetch import _CHAIN_HOP_DISCOUNT
    plan = board.phase
    assert pilot._grab_value_of(board, SOLROCK, plan) == 22
    expected = _CHAIN_HOP_DISCOUNT * _CHAIN_HOP_DISCOUNT * 22
    assert pilot._chain_grab_value(board, PETREL, plan) == pytest.approx(expected)


@pytest.mark.req("REQ-GEN-0077")
def test_chain_is_zero_for_a_non_tutor(pilot, board):
    """A card with no deck FETCH clause (Judge — a draw Supporter) prices chain 0: the endorser
    fail direction (unknown chain → 0, never inflates)."""
    assert pilot._chain_grab_value(board, JUDGE, board.phase) == 0.0


@pytest.mark.req("REQ-GEN-0077")
def test_supporter_chain_dies_with_the_slot_spent(pilot, board):
    """Opportunity cost (seam doc §3): a Supporter tutor with the one-per-turn Supporter slot
    already spent prices chain 0 — the chain is not free this turn (fail-closed)."""
    spent = replace(board, supporter_played=True)
    assert pilot._chain_grab_value(spent, PETREL, spent.phase) == 0.0


@pytest.mark.req("REQ-GEN-0077")
def test_chain_decays_once_the_end_target_is_acquired(pilot, board):
    """The `_greedy_grab` invariant: with Solrock (virtually) in play, `fetch-the-missing-engine-
    half` stands down, the chain's best end value collapses to noise (the +3 color tie-break), and
    the discounted chain drops below the opener floor — the rung goes silent on a re-score."""
    from common.strategy.doctrines.doctrine_fetch import _CHAIN_OPENER_FLOOR
    vboard = replace(board, in_play_ids=board.in_play_ids | {SOLROCK})
    plan = vboard.phase
    assert pilot._grab_value_of(vboard, SOLROCK, plan) == 0
    assert pilot._chain_grab_value(vboard, PETREL, plan) < _CHAIN_OPENER_FLOOR


def _hop_obs(base: dict, pulled: tuple, option_pred, pilot) -> dict:
    """The NEXT select after the grabbed tutor is PLAYED, synthesized from the recorded board: the
    pulled card (id, serial) moves deck → my discard, the one-per-turn Supporter slot is spent
    (Petrel opened the chain), and the new select's options are the deck entries matching
    ``option_pred`` (the fetched tutor's clause targets, as the engine would offer them)."""
    obs = copy.deepcopy(base)
    state = obs["current"]
    state["supporterPlayed"] = True
    me = state["players"][0]
    sel = obs["select"]
    pid, pserial = pulled
    sel["deck"] = [c for c in sel["deck"] if not (c["id"] == pid and c["serial"] == pserial)]
    me["discard"] = (me.get("discard") or []) + [{"id": pid, "playerIndex": 0, "serial": pserial}]
    me["deckCount"] = len(sel["deck"])
    sel["option"] = [{"area": 1, "index": i, "playerIndex": 0, "type": 3}
                     for i, c in enumerate(sel["deck"]) if option_pred(pilot.stats.get(c["id"]))]
    return obs


@pytest.mark.req("REQ-GEN-0077")
def test_hop_two_petrel_select_takes_a_free_item_tutor(pilot, rec):
    """The EXECUTED chain, hop 2: Petrel is played (Supporter slot spent), its Trainer select is
    on the menu. The chain rung recurses — every Item tutor reaching Solrock fires it — and the
    pick is a FREE one (Fighting Gong or the equivalent Poké Pad), with the discard-2 Ultra Ball
    demoted below them (`demote-the-costly-chain-opener` −2: the flat band is cost-blind, the
    tie-break is not). The Supporters are dead this turn (`grab-what-i-can-play-this-turn`)."""
    is_trainer = lambda st: st is not None and not st.is_pokemon and not st.is_energy
    obs = _hop_obs(rec["obs"], (PETREL, 55), is_trainer, pilot)
    dec = pilot.explain(obs)
    assert len(dec.chosen) == 1
    picked = dec.options[dec.chosen[0]]
    assert picked.card_id in (FIGHTING_GONG, POKE_PAD)
    assert any(h.id == "grab-the-chain-opener" for h, _ in picked.fired)
    by_card = {}
    for t in dec.options:
        by_card.setdefault(t.card_id, t)
    assert by_card[ULTRA_BALL].score < by_card[FIGHTING_GONG].score
    assert any(h.id == "demote-the-costly-chain-opener" for h, _ in by_card[ULTRA_BALL].fired)


@pytest.mark.req("REQ-GEN-0077")
def test_hop_three_gong_select_takes_the_solrock(pilot, rec):
    """The EXECUTED chain, hop 3: Fighting Gong is played, its select (Basic {F} Pokémon / Basic
    {F} Energy) is on the menu — Solrock (`fetch-the-missing-engine-half` +22) wins over the
    Makuhita line piece (+18), the {F} Energy (+3, a copy is already in hand) and the redundant
    engine/base pieces. The chain the human named lands on its END target."""
    is_trainer = lambda st: st is not None and not st.is_pokemon and not st.is_energy
    obs1 = _hop_obs(rec["obs"], (PETREL, 55), is_trainer, pilot)
    gong = next(c for c in obs1["select"]["deck"] if c["id"] == FIGHTING_GONG)

    def gong_target(st):
        if st is None:
            return False
        if st.is_basic_energy and getattr(st, "energyType", None) == _FIGHTING:
            return True
        return st.is_pokemon and not getattr(st, "evolvesFrom", None)   # Basic ({F} — mono-type deck)

    obs2 = _hop_obs(obs1, (FIGHTING_GONG, gong["serial"]), gong_target, pilot)
    dec = pilot.explain(obs2)
    assert len(dec.chosen) == 1
    assert dec.options[dec.chosen[0]].card_id == SOLROCK


MAKUHITA, HARIYAMA = 673, 674


def _petrel_select(rec, pilot, *, makuhita_in_hand=False, poke_pads_in_pool=None):
    """Petrel's Trainer select (hop 2), optionally with Makuhita in hand (Hariyama becomes the
    wanted evolution) and the pool thinned to ``poke_pads_in_pool`` Poké Pad copies (None = all)."""
    is_trainer = lambda st: st is not None and not st.is_pokemon and not st.is_energy
    obs = _hop_obs(rec["obs"], (PETREL, 55), is_trainer, pilot)
    me = obs["current"]["players"][0]
    sel = obs["select"]
    if makuhita_in_hand:
        me["hand"] = me["hand"] + [{"id": MAKUHITA, "playerIndex": 0, "serial": 99}]
    if poke_pads_in_pool is not None:
        kept, deck = 0, []
        for c in sel["deck"]:
            if c["id"] == POKE_PAD:
                if kept >= poke_pads_in_pool:
                    continue
                kept += 1
            deck.append(c)
        sel["deck"] = deck
        me["deckCount"] = len(deck)
        sel["option"] = [{"area": 1, "index": i, "playerIndex": 0, "type": 3}
                         for i, c in enumerate(deck) if is_trainer(pilot.stats.get(c["id"]))]
    return obs


@pytest.mark.req("REQ-GEN-0077")
def test_dont_spend_the_last_route_to_a_wanted_evolution(pilot, rec):
    """The Gong-vs-Poké-Pad hop pick, scarcity-gated: with Makuhita down (its Hariyama is now the
    wanted evolution) and the pool's LAST Poké Pad on offer, spending it as the chain hop would
    close the only FREE route to Hariyama (Gong's `basic_pokemon` clause cannot reach a Stage 1;
    Ultra Ball reaches it but at discard-2, not free). `dont-spend-the-last-route-to-a-wanted-
    evolution` (−2) breaks the +15 tie toward Gong: Petrel → GONG → Solrock, preserving Poké Pad."""
    obs = _petrel_select(rec, pilot, makuhita_in_hand=True, poke_pads_in_pool=1)
    dec = pilot.explain(obs)
    picked = dec.options[dec.chosen[0]]
    assert picked.card_id == FIGHTING_GONG
    by_card = {}
    for t in dec.options:
        by_card.setdefault(t.card_id, t)
    pad = by_card[POKE_PAD]
    assert any(h.id == "dont-spend-the-last-route-to-a-wanted-evolution" for h, _ in pad.fired)
    assert pad.score < by_card[FIGHTING_GONG].score


@pytest.mark.req("REQ-GEN-0077")
def test_abundant_copies_keep_the_hop_tie(pilot, rec):
    """The scarcity gate: with Makuhita down but ALL FOUR Poké Pad copies still in the pool,
    spending one closes nothing — the rung stays silent on every option and the free hops keep
    their +15 tie (the preference is only real at scarcity)."""
    obs = _petrel_select(rec, pilot, makuhita_in_hand=True)
    dec = pilot.explain(obs)
    for t in dec.options:
        assert not any(h.id == "dont-spend-the-last-route-to-a-wanted-evolution"
                       for h, _ in t.fired)
    assert dec.options[dec.chosen[0]].card_id in (FIGHTING_GONG, POKE_PAD)


@pytest.mark.req("REQ-GEN-0077")
def test_no_wanted_evolution_no_preservation(pilot, rec):
    """Without Makuhita in play or hand there is no wanted evolution (the recorded board): even the
    LAST Poké Pad is spent freely — the rung is need-gated, not a blanket Poké-Pad floor."""
    obs = _petrel_select(rec, pilot, poke_pads_in_pool=1)
    dec = pilot.explain(obs)
    for t in dec.options:
        assert not any(h.id == "dont-spend-the-last-route-to-a-wanted-evolution"
                       for h, _ in t.fired)


@pytest.mark.req("REQ-GEN-0077")
def test_chain_graph_is_full_scope_and_cycle_safe(pilot, board):
    """The graph leg: Petrel's `trainer` clause reaches the deck's Trainers — including Fighting
    Gong (the chain's Item hop) and Petrel ITSELF (the cycle the path-`seen` set + Item-only
    descent must cut; the recursion above terminating IS the cycle-safety proof). Never a Pokémon
    or an Energy (clauses only, `fetch_closure.fetch_target_matches`)."""
    targets = pilot._chain_fetch_targets(PETREL)
    assert FIGHTING_GONG in targets
    assert PETREL in targets                      # self-reach: cut at value time, present in graph
    assert SOLROCK not in targets                 # a Pokémon is not a `trainer` target
    assert 6 not in targets                       # nor is a Basic Energy
