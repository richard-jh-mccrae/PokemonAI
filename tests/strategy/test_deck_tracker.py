"""Deck tracker (own-card perfect-information model) — `common.deck_tracker.OwnCardModel`.

Lib-free synthetic observations. The model resolves the fixed 6-card prize pile from a full search
reveal, then derives the exact deck every turn; soundness = it NEVER asserts a false certainty (it
drops the anchor on any desync). The Board consumes the resolved prizes for prize-EXACT deck knowledge.
"""
import pytest

from common.deck_tracker import OwnCardModel
from common.pilot import Pilot
from common.strategy import Strategy

# A small known "decklist": 3×id1, 3×id2, 4×id3 (10 cards). Same arithmetic as real 60-card deck.
DECK = [1, 1, 1, 2, 2, 2, 3, 3, 3, 3]


def _poke(cid, serial=None):
    p = {"id": cid, "energyCards": [], "tools": [], "preEvolution": []}
    if serial is not None:
        p["serial"] = serial
    return p


def _take(cid, serial, player=0):
    """One PRIZE->HAND log entry: the engine names the exact card instance taken as a prize."""
    return {"cardId": cid, "serial": serial, "playerIndex": player,
            "fromArea": 6, "toArea": 2, "type": 6}


def _obs(*, deck_count, prize, hand=(), discard=(), active=None, bench=(),
         reveal=None, effect=None, turn=2, logs=(), active_serial=None,
         effect_serial=None, context_card=None):
    """An observation the tracker reads: my zones + `deckCount` + (optionally) a search that reveals
    the deck (`reveal`) and names the resolving card (`effect`), plus the engine's `logs` delta.

    `active_serial` / `effect_serial` / `context_card` model an ABILITY resolving off a Pokémon that
    is still in play — the engine names it by `serial`, and it is already counted in its zone."""
    me = {
        "hand": [{"id": c} for c in hand],
        "discard": [{"id": c} for c in discard],
        "active": [_poke(active, active_serial)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "prize": [None] * prize,
        "deckCount": deck_count,
    }
    eff = None
    if effect is not None:
        eff = {"id": effect}
        if effect_serial is not None:
            eff["serial"] = effect_serial
    select = {
        "context": 7, "option": [], "contextCard": context_card,
        "deck": [{"id": c} for c in reveal] if reveal is not None else None,
        "effect": eff,
    }
    return {"current": {"turn": turn, "yourIndex": 0, "players": [me, None]},
            "select": select, "logs": list(logs)}


# ----------------------------------------------------------------------- anchoring
@pytest.mark.req("REQ-GEN-0034")
def test_anchor_resolves_prizes_exactly_from_a_full_reveal():
    m = OwnCardModel(DECK)
    # visible {1:1}; deck (6 cards) revealed; prizes_remaining 3 -> prizes = decklist−deck−visible.
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))
    assert m.prize_export() == {1: 2, 2: 1}            # other 2× id1 and 1× id2 are prized


@pytest.mark.req("REQ-GEN-0034")
def test_resolving_effect_card_is_counted_as_visible():
    m = OwnCardModel(DECK)
    # Search card (id1) is resolving: not in deck reveal, not in any zone — named by effect.
    # Without counting it, prize total would be 3 (≠ remaining 2) and would NOT anchor.
    m.observe(_obs(deck_count=7, prize=2, hand=[], effect=1, reveal=[1, 1, 2, 2, 2, 3, 3]))
    assert m.prize_export() == {3: 2}


@pytest.mark.req("REQ-GEN-0034")
def test_partial_reveal_does_not_anchor():
    m = OwnCardModel(DECK)
    # select.deck shorter than deckCount (filtered candidate list) -> never anchor off a subset.
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2]))
    assert m.prize_export() is None


# ----------------------------------------------------------------------- maintenance
@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_reconciles_uniquely():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))   # prizes {1:2, 2:1}
    # A KO takes a prized id1 into hand (remaining 3->2, no reveal). Uniquely reconciled: drop one id1.
    m.observe(_obs(deck_count=6, prize=2, hand=[1, 1]))
    assert m.prize_export() == {1: 1, 2: 1}


@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_falls_back_when_ambiguous():
    m = OwnCardModel(DECK)
    # prizes {3:2}; id3 also still in deck, so after a take the lost copy is ambiguous -> fall back.
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    assert m.prize_export() == {3: 2}
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3]))
    assert m.prize_export() is None                   # which prized id3 was taken is unknowable -> no guess


@pytest.mark.req("REQ-GEN-0034")
def test_resolving_ability_card_still_in_play_is_not_double_counted():
    """An ABILITY resolves off a Pokémon that is STILL IN PLAY (Drakloak's Recon Directive), so the
    `effect` rider's premise — "it has left the deck but sits in no zone" — is false and the card is
    already counted in its zone. Counting it twice pushed `visible` past the decklist and dropped the
    anchor for a desync that never happened. The engine names it by `serial`, so dedupe on that."""
    m = OwnCardModel(DECK)
    # All 3× id1 visible: 2 in hand + the Active (serial 7). Prizes {2:1, 3:2}.
    anchor = dict(deck_count=4, prize=3, hand=[1, 1], active=1, active_serial=7)
    m.observe(_obs(**anchor, reveal=[2, 2, 3, 3]))
    assert m.prize_export() == {2: 1, 3: 2}
    # The Active's OWN ability resolves — same physical card, named by serial.
    m.observe(_obs(**anchor, effect=1, effect_serial=7))
    assert m.prize_export() == {2: 1, 3: 2}            # anchor survives; it was never a desync


@pytest.mark.req("REQ-GEN-0034")
def test_resolving_card_named_twice_counts_once():
    """`effect` and `contextCard` can name the SAME physical card; dedupe by serial covers that too."""
    m = OwnCardModel(DECK)
    # 3× id3 in discard + the 4th resolving (serial 42, named by BOTH keys) = 4 visible, not 5.
    m.observe(_obs(deck_count=3, prize=3, discard=[3, 3, 3], reveal=[1, 1, 2],
                   effect=3, effect_serial=42, context_card={"id": 3, "serial": 42}))
    assert m.prize_export() == {1: 1, 2: 2}


@pytest.mark.req("REQ-GEN-0034")
def test_resolving_card_not_in_any_zone_is_still_counted():
    """The rider still does its job for a card genuinely in limbo — a played Trainer whose serial
    matches nothing in a zone (and, per the test above, one carrying no serial at all)."""
    m = OwnCardModel(DECK)
    # id1 resolving (serial 99, in no zone): without counting it, prizes would be 3 ≠ remaining 2.
    m.observe(_obs(deck_count=7, prize=2, hand=[], effect=1, effect_serial=99,
                   reveal=[1, 1, 2, 2, 2, 3, 3]))
    assert m.prize_export() == {3: 2}


@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_is_resolved_exactly_from_the_log():
    """The engine NAMES the card taken as a prize (`logs` PRIZE->HAND carries `cardId`/`serial`),
    so the ambiguous case above must resolve rather than drop the anchor."""
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    assert m.prize_export() == {3: 2}
    # Same frame as test_prize_take_falls_back_when_ambiguous — but the log names WHICH id3 left.
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3], logs=[_take(3, serial=99)]))
    assert m.prize_export() == {3: 1}


@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_log_is_idempotent():
    """`logs` is a DELTA, not a cumulative stream, and the same card instance must never be counted
    twice — takes are accumulated by `serial` (unique per physical card, engine-verified)."""
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    take = _obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3], logs=[_take(3, serial=99)])
    m.observe(take)
    m.observe(take)                                   # replayed frame: must not double-count
    assert m.prize_export() == {3: 1}


@pytest.mark.req("REQ-GEN-0034")
def test_opponent_prize_take_is_never_consumed():
    """The opponent's prize takes carry no `cardId` and are not ours — they must not touch MY model."""
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2],
                   logs=[{"fromArea": 6, "toArea": 2, "playerIndex": 1, "type": 6}]))
    assert m.prize_export() == {3: 2}                  # unchanged — not my take


@pytest.mark.req("REQ-GEN-0034")
def test_prize_take_without_a_log_still_falls_back():
    """No log entry (or one lacking `serial`/`cardId`) -> the sound pre-#175 behaviour is unchanged."""
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3]))
    assert m.prize_export() is None                    # unknowable without the log -> no guess


@pytest.mark.req("REQ-GEN-0034")
def test_reset_clears_recorded_prize_takes():
    """Takes are match state: a new match must not inherit the previous match's prize takes."""
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3]))
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3], logs=[_take(3, serial=99)]))
    m.reset()
    m.observe(_obs(deck_count=2, prize=2, hand=[1, 1, 1, 2, 2, 2], reveal=[3, 3], turn=2))
    # A take with the SAME serial in the new match is a different physical card and must register.
    m.observe(_obs(deck_count=2, prize=1, hand=[1, 1, 1, 2, 2, 2, 3], logs=[_take(3, serial=99)]))
    assert m.prize_export() == {3: 1}


@pytest.mark.req("REQ-GEN-0034")
def test_desync_drops_the_anchor():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))   # prizes {1:2, 2:1}
    assert m.prize_export() is not None
    # All 3× id1 now visible while 2 were "prized" and prize count didn't drop -> contradiction.
    m.observe(_obs(deck_count=4, prize=3, hand=[1, 1, 1]))
    assert m.prize_export() is None


@pytest.mark.req("REQ-GEN-0034")
def test_reset_on_match_start_and_turn_backwards():
    m = OwnCardModel(DECK)
    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3]))
    assert m.prize_export() is not None
    m.observe({"select": None})                       # deck-submission step = a new match
    assert m.prize_export() is None

    m.observe(_obs(deck_count=6, prize=3, hand=[1], reveal=[2, 2, 3, 3, 3, 3], turn=5))
    assert m.prize_export() is not None
    m.observe(_obs(deck_count=6, prize=3, hand=[1], turn=1))   # turn went backwards -> reset, no reveal
    assert m.prize_export() is None


@pytest.mark.req("REQ-GEN-0034")
def test_observe_never_raises_on_garbage():
    m = OwnCardModel(DECK)
    for bad in ({}, {"select": {}}, {"current": None, "select": {"deck": [None]}}, {"select": {"deck": 5}}):
        m.observe(bad)                                # must not raise (grader safety)
    assert m.prize_export() is None


# ----------------------------------------------------------------------- Board integration
def _board_obs(*, hand=(), discard=(), active=None, bench=(), prizes=None):
    me = {
        "hand": [{"id": c} for c in hand], "discard": [{"id": c} for c in discard],
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "prize": [None] * (sum(prizes.values()) if prizes else 0), "deckCount": 0,
    }
    return {"current": {"turn": 2, "yourIndex": 0, "players": [me, None]},
            "select": {"context": 0, "option": [{"type": 14}]}, "own_prizes": prizes}


@pytest.mark.req("REQ-GEN-0034")
def test_board_is_prize_exact_with_the_tracker_annotation():
    pilot = Pilot(Strategy(), deck=DECK)
    # visible {1:1, 2:1}; resolved prizes {1:2, 2:1} -> deck = {1:0, 2:1, 3:4}.
    b = pilot._board(_board_obs(hand=[1], active=2, prizes={1: 2, 2: 1}))
    assert b.deck_definitely_empty_of(1)              # 1 visible + 2 prized -> EXACTLY 0 in deck
    assert not b.deck_definitely_empty_of(2)
    assert b.deck_definitely_has(2) and b.deck_definitely_has(3)
    assert not b.deck_definitely_has(1)               # all id1 accounted (visible + prized)


@pytest.mark.req("REQ-GEN-0034")
def test_board_without_annotation_keeps_the_sound_stateless_oracle():
    pilot = Pilot(Strategy(), deck=DECK)
    # No own_prizes: stateless. id1 has 1 visible of 3 -> rest could be prized -> NOT empty,
    # and no positive claim made (deck_definitely_has is False without certainty).
    b = pilot._board(_board_obs(hand=[1], active=2, prizes=None))
    assert not b.deck_definitely_empty_of(1)
    assert b.deck_known_counts is None
    assert not b.deck_definitely_has(2)
