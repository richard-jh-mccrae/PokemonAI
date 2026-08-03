"""The greedy policy's ordering is **canonical**, not positional (ADR-0103, Issue #254).

`_evaluate` ranked options by ``(score, attach_to_needy_line)`` and let an EXACT tie fall to the
engine's menu index. That index is the one thing about an option that is not a board fact: after an
identical first step onto interchangeable bodies, the resulting boards are isomorphic but their menus
are permutations of each other, so the same tie resolved to a different body on each — which is how
`_engine_leaf_value`'s within-turn rollout reached a KO from bench 0 and missed the isomorphic line
from bench 1 (`81903490|0|decision|49`: 1167.0 / 95.4 / 95.4 on three byte-identical Riolu).

The fix replaces the positional tie-break with the ADR-0091 fingerprint — the option's Option
Equivalence Class identity, which is a pure function of the board. These tracers pin the ordering
seam directly (`_score_order`), with traces handed in, so the property is provable without the engine:
**permuting the menu must not change which option the policy picks.**
"""
import pytest

from common.cards import CardFunctions
from common.option_equivalence import AREA_BENCH, AREA_DECK, AREA_HAND
from common.pilot import OptionTrace, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy
from common.strategy.context import _TO_HAND
from common.strategy.general_strategy import GENERAL_STRATEGY

CID = 1030
OPT_CARD = 3


def _pilot():
    stats = DictCardStatProvider({CID: CardStat(CID, synthetic=True, name="riolu", hp=70, energyType=3)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({}))


def _body(*, hp, serial):
    return {"appearThisTurn": False, "energies": [], "energyCards": [], "hp": hp, "id": CID,
            "maxHp": 70, "playerIndex": 0, "preEvolution": [], "serial": serial, "tools": []}


def _obs(bench):
    return {"current": {"yourIndex": 0, "players": [{"active": [], "bench": list(bench),
                                                     "hand": [], "discard": []}, {}]}}


def _bench_opts(n):
    return [{"area": AREA_BENCH, "index": i, "playerIndex": 0, "type": OPT_CARD} for i in range(n)]


def _trace(index, score, *, needy=False):
    return OptionTrace(index=index, score=score, plan=Plan.SETUP, card_id=CID, fired=[],
                       attach_to_needy_line=needy)


def _picked_body(pilot, bench):
    """Which BODY the ordering puts first — the identity that must survive a permutation, since the
    index deliberately does not."""
    opts = _bench_opts(len(bench))
    order = pilot._score_order(_obs(bench), opts, [_trace(i, 0.0) for i in range(len(bench))])
    return bench[order[0]]


@pytest.mark.req("REQ-PILOT-0028")
def test_an_exact_tie_picks_the_SAME_body_from_a_permuted_menu():
    """The Issue #254 property. Two distinguishable bodies (one damaged), both scoring exactly 0.0 — the
    live case, since most options score 0.0 and the tie is the norm rather than the exception. Under
    the old positional tie-break each menu picked its own option 0, i.e. a different body."""
    p = _pilot()
    fresh, hurt = _body(hp=70, serial=1), _body(hp=40, serial=2)
    assert _picked_body(p, [fresh, hurt]) == _picked_body(p, [hurt, fresh])


@pytest.mark.req("REQ-PILOT-0028")
def test_the_permutation_invariance_holds_across_a_three_body_menu():
    """Three bodies, six orderings, one decision — the `81903490|0|decision|49` shape with the twins
    split apart so the class collapse is not what is doing the work."""
    p = _pilot()
    bodies = [_body(hp=70, serial=1), _body(hp=40, serial=2), _body(hp=10, serial=3)]
    picks = {_picked_body(p, [bodies[i], bodies[j], bodies[k]])["serial"]
             for i, j, k in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))}
    assert len(picks) == 1                           # serial is the body's identity, not its slot


@pytest.mark.req("REQ-PILOT-0028")
def test_score_still_outranks_the_canonical_key():
    """The tie-break is a TIE-break: it may only order options the scoring already called equal."""
    p = _pilot()
    bench = [_body(hp=70, serial=1), _body(hp=40, serial=2)]
    for winner in (0, 1):
        traces = [_trace(i, 9.0 if i == winner else 1.0) for i in range(2)]
        assert p._score_order(_obs(bench), _bench_opts(2), traces)[0] == winner


@pytest.mark.req("REQ-PILOT-0028")
def test_the_needy_line_attach_tiebreak_still_outranks_the_canonical_key():
    """`ep82867148 f87`'s ordering nicety keeps its place: among EQUAL-score attaches the needy Line
    base goes first, and only options that key equal on BOTH fall to the canonical key."""
    p = _pilot()
    bench = [_body(hp=70, serial=1), _body(hp=40, serial=2)]
    for needy in (0, 1):
        traces = [_trace(i, 0.0, needy=(i == needy)) for i in range(2)]
        assert p._score_order(_obs(bench), _bench_opts(2), traces)[0] == needy


@pytest.mark.req("REQ-PILOT-0028")
def test_the_greedy_grab_picks_the_same_cards_from_a_permuted_menu():
    """The multi-pick path is the same defect: `_greedy_grab` took ``max(..., key=(score, -j))``, so a
    grab tie also fell to the menu index. It re-scores between picks, so it cannot simply consume
    `_score_order`'s list — it takes the same canonical key instead."""
    p = _pilot()
    p._virtual_grab_board = lambda *a, **k: None                  # the re-score is not what is tested
    p._option_trace = lambda obs, select, board, o, k: _trace(k, 1.0)
    cards = [_body(hp=70, serial=1), _body(hp=40, serial=2), _body(hp=10, serial=3)]
    select = {"context": _TO_HAND, "option": None}

    def grabbed(order):
        hand = [cards[i] for i in order]
        opts = [{"area": AREA_HAND, "index": i, "playerIndex": 0, "type": OPT_CARD}
                for i in range(len(hand))]
        obs = {"current": {"yourIndex": 0,
                           "players": [{"active": [], "bench": [], "hand": hand, "discard": []}, {}]}}
        picks = p._greedy_grab(obs, {**select, "option": opts}, None,
                               [_trace(i, 1.0) for i in range(len(hand))], opts, 0, 2)
        return sorted(hand[i]["serial"] for i in picks)

    assert grabbed((0, 1, 2)) == grabbed((2, 0, 1)) == grabbed((1, 2, 0))


@pytest.mark.req("REQ-PILOT-0028")
def test_unfingerprintable_options_keep_their_menu_order_among_themselves():
    """A face-down DECK option has no canonical identity to order by, so the sort must stay stable
    over them rather than invent one — blind ⇒ conservative, the same rule the oracle itself keeps."""
    p = _pilot()
    opts = [{"area": AREA_DECK, "index": i, "playerIndex": 0, "type": OPT_CARD} for i in range(3)]
    order = p._score_order(_obs([]), opts, [_trace(i, 0.0) for i in range(3)])
    assert order == [0, 1, 2]
