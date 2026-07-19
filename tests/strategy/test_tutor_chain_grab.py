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

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

PETREL, FIGHTING_GONG, JUDGE, LILLIES = 1219, 1142, 1213, 1227
SOLROCK, MEGA_LUCARIO_EX = 676, 678


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
