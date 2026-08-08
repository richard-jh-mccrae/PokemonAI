"""Seam 4 (Issue #213): the scaled threat rank on REAL corpus frames, through a real Pilot.

Zero decided-pick flips proves the swap is SAFE but proves nothing about the fix FIRING, and a rank
change that never fires is indistinguishable from one that isn't wired. These tests close that gap
from the other side.

Driven by `train.tune._build_pilot` against the real card provider and a real captured `obs`: a
hand-built stat table can describe a board that cannot exist and manufacture a passing test.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CLEFAIRY_EX = 272                     # Full Moon Rondo: printed 20, +20 per COMBINED bench body
KADABRA, ALAKAZAM = 742, 743          # Powerful Hand: printed 0, 20 per card in hand


def _corpus():
    """Every committed Correction carrying a replayable `obs`, keyed by frame — through THE Corpus
    Reader (ADR-0087 / ADR-0089), which selects frames by board content rather than by literal ids."""
    from corpus_helpers import corpus_index
    return corpus_index()


def _opp_bodies(obs):
    state = obs.get("current") or {}
    players = state.get("players") or []
    yi = state.get("yourIndex", 0)
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
    return [b for b in ((opp.get("active") or []) + (opp.get("bench") or [])) if b]


def _frames_containing(corpus, card_ids):
    return [(k, r) for k, r in sorted(corpus.items())
            if any(b.get("id") in card_ids for b in _opp_bodies(r.obs))]


@pytest.fixture(scope="module")
def corpus():
    c = _corpus()
    if not c:
        pytest.skip("no committed corrections corpus in this checkout")
    return c


def _pair_on_real_frame(rec, card_ids):
    """`{cid: (own_off, fwd_off, own_on, fwd_on)}`, keyed by CARD id rather than body: the read is a
    card fact, so a second copy of the same card only repeats the first."""
    from train.tune import _build_pilot
    wanted = {b.get("id") for b in _opp_bodies(rec.obs) if b.get("id") in card_ids}
    out = {cid: [] for cid in wanted}
    for on in (False, True):
        pilot = _build_pilot(rec.agent)[0]
        pilot.scaled_threat_rank = on
        pilot.explain(rec.obs)                     # builds the per-decision damage context
        for cid in wanted:
            out[cid].extend(pilot._threat_damage_pair(cid, pilot.stats.get(cid)))
    return {cid: tuple(v) for cid, v in out.items()}


@pytest.mark.req("REQ-GEN-0028")
def test_the_corpus_really_contains_the_cards_this_issue_is_about(corpus):
    # Guard against a vacuous pass: if the corpus stopped containing these cards, the tests below
    # would skip and read green for the wrong reason.
    assert _frames_containing(corpus, {CLEFAIRY_EX}), "no Lillie's Clefairy ex frames"
    assert _frames_containing(corpus, {KADABRA, ALAKAZAM}), "no Kadabra/Alakazam frames"


@pytest.mark.req("REQ-GEN-0028")
def test_a_combined_bench_attacker_outprices_its_printed_damage_on_a_real_frame(corpus):
    frames = _frames_containing(corpus, {CLEFAIRY_EX})
    fired = []
    for _key, rec in frames:
        pairs = _pair_on_real_frame(rec, {CLEFAIRY_EX})
        for _cid, (own_off, _fwd_off, own_on, _fwd_on) in pairs.items():
            assert own_off == 20                       # printed Full Moon Rondo
            assert own_on >= own_off                   # the scaler never subtracts
            if own_on > own_off:
                fired.append(own_on)
    assert fired, ("the scaled read never exceeded printed damage on any real Lillie's Clefairy ex "
                   "frame — the fix is not firing where the issue said it would")
    assert max(fired) >= 60                            # at least two benched bodies in play


@pytest.mark.req("REQ-GEN-0028")
def test_a_hand_size_line_outprices_its_printed_forward_index_on_a_real_frame(corpus):
    # The `ms f85` gap in its natural habitat: Kadabra's line reaches Alakazam, whose printed damage
    # is 0, so the printed forward index reads 10 and the line looks harmless.
    frames = _frames_containing(corpus, {KADABRA, ALAKAZAM})
    fired = []
    for _key, rec in frames:
        pairs = _pair_on_real_frame(rec, {KADABRA, ALAKAZAM})
        for cid, (own_off, fwd_off, own_on, fwd_on) in pairs.items():
            best_off, best_on = max(own_off, fwd_off), max(own_on, fwd_on)
            assert best_on >= best_off
            if best_on > best_off:
                fired.append((cid, best_off, best_on))
    assert fired, ("the scaled read never exceeded the printed read on any real Kadabra/Alakazam "
                   "frame — the ms f85 gap is not actually being closed")
