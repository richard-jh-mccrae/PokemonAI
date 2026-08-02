"""The deadline gate library (ADR-0065; grill Rounds 8-9; scope plan doc retired — all four legs built).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The gate supplies the
first factor of that difference as ``deploy_odds`` — P(the card's ROLE is realisable by its deadline) —
so a held evolution whose base is provably gone (a dead card) is cheap to shuffle/gamble away, while a
deployable one keeps its full worth. A PARAMETER of the one keep-value equation, never a new rung.
"""
import pytest

from common import gate_library


class _Stat:
    def __init__(self, evolvesFrom=None, name=None):
        self.evolvesFrom = evolvesFrom
        self.name = name


@pytest.mark.req("REQ-GATE-0001")
def test_is_evolution_reads_evolves_from():
    assert gate_library.is_evolution(_Stat(evolvesFrom="Staryu")) is True
    assert gate_library.is_evolution(_Stat(evolvesFrom=None)) is False
    assert gate_library.is_evolution(None) is False


@pytest.mark.req("REQ-GATE-0001")
def test_deploy_odds_is_one_for_a_non_evolution():
    """A Basic / Trainer / Energy realises its role by being held — no evolution deadline, full worth."""
    basic = _Stat(evolvesFrom=None, name="Cinderace")
    assert gate_library.deploy_odds(basic) == 1.0
    assert gate_library.deploy_odds(None) == 1.0


@pytest.mark.req("REQ-GATE-0001")
def test_deploy_odds_prices_the_playability_verdict_and_defaults_to_keep():
    """The gate is the ARITHMETIC only: a playable evolution keeps full worth, an unplayable one
    collapses to 0 (ep83966336 f44 — a Mega Lucario ex with every Riolu evolved/gone is a dead card,
    so its keep-value collapses and a refresh shuffles it to dig). WHETHER it is playable is
    `common.playability`'s backward walk (ADR-0103, Issue #288), resolved by the caller: the three
    zone booleans this used to OR together here were only its shallowest correct version, blind to
    the ``evolvesFrom`` chain and to Rare Candy. The default is ``playable=True`` — an unsure caller
    discounts nothing, the same fail-open direction as every other gate in this module."""
    mega = _Stat(evolvesFrom="Riolu", name="Mega Lucario ex")
    assert gate_library.deploy_odds(mega, playable=True) == 1.0
    assert gate_library.deploy_odds(mega) == 1.0
    assert gate_library.deploy_odds(mega, playable=False) == 0.0


@pytest.mark.req("REQ-GATE-0005")
def test_need_met_odds_gates_a_satisfied_role():
    """The need-met gate (the fetcher gate's cousin — a role SATISFIED rather than a target dead):
    0.0 when a card's reason-to-keep is already fulfilled by the board, 1.0 otherwise; errs toward
    keep."""
    assert gate_library.need_met_odds(need_met=True) == 0.0
    assert gate_library.need_met_odds(need_met=False) == 1.0
    assert gate_library.need_met_odds() == 1.0


@pytest.mark.req("REQ-GATE-0005")
def test_pilot_deploy_odds_gates_a_redundant_wincon_tutor():
    """The redundant-tutor need gate (ladder-win case 82753102-16): a `rush_evolve` / `tutor_mega`
    wincon-tutor whose wincon is already IN HAND has its role MET — it has nothing left worth
    fetching — so `_deploy_odds` collapses to 0 and its keep-cost with it. A REAL gate: it fires
    live wherever `keep_cost` is consumed (the gamble keep-floor, the refresh SHED), not only the
    discard shadow. 1.0 when the wincon is not in hand (the tutor is still live)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    ms = _build_pilot("mega_starmie")[0]
    sal = 1189                                                    # Salvatore: a rush_evolve wincon-tutor
    assert "rush_evolve" in ms.functions.tags(sal)
    assert ms._role_value(sal) > 0                                # it has worth to gate away
    counts = {sal: 1}
    assert ms._deploy_odds(sal, Board(wincon_in_hand=False), counts) == 1.0
    assert ms._deploy_odds(sal, Board(wincon_in_hand=True), counts) == 0.0
    assert ms._keep_cost(sal, counts, 40, 6, Board(wincon_in_hand=True)) == 0.0
    assert ms._keep_cost(sal, counts, 40, 6, Board(wincon_in_hand=False)) > 0.0


@pytest.mark.req("REQ-GATE-0002")
def test_fetch_deploy_odds_gates_a_dead_fetcher():
    """The fetcher gate (searcher/recycler leg — acceptance pin ep83457493 f31): a fetch Trainer whose
    every target is PROVABLY dead realises no role (0.0 → sheds freely, Ultra-Ball fodder); anything
    less than proven deadness keeps full worth (1.0 — errs toward keep, like the evolution gate)."""
    assert gate_library.fetch_deploy_odds(targets_exhausted=True) == 0.0
    assert gate_library.fetch_deploy_odds(targets_exhausted=False) == 1.0
    assert gate_library.fetch_deploy_odds() == 1.0


@pytest.mark.req("REQ-GATE-0003")
def test_closing_gate_zeroes_the_reaccess_credit():
    """The pressure gate's primitive (spec Round 8 §3: gates CLOSE, and a closing edge SPIKES
    keep-cost): P(met | shuffle) counts re-access only if it arrives before the gate closes. When
    the card's gate is closing NOW, a probabilistic redraw is not an answer the plan can bank on —
    the re-access credit is zeroed, so keep_cost charges the full role worth. Pass-through
    otherwise."""
    assert gate_library.closing_gate_reaccess(0.7) == 0.7
    assert gate_library.closing_gate_reaccess(0.7, gate_closing=False) == 0.7
    assert gate_library.closing_gate_reaccess(0.7, gate_closing=True) == 0.0
    assert gate_library.closing_gate_reaccess(0.0, gate_closing=True) == 0.0


@pytest.mark.req("REQ-GATE-0006")
def test_deploy_now_spike_keeps_a_hand_evolution_with_an_eligible_base():
    """The DEPLOY-NOW spike (the discard convergence's flagship, ep86091435 f68): a hand evolution
    whose `evolvesFrom` base is in play AND ELIGIBLE (a matching body in play since last turn,
    `appearThisTurn` False, turn ≥ 2) can be played THIS turn — pitching/shuffling it forfeits a live
    tempo play its re-access can't restore (you need it NOW). So its closing gate fires and its keep
    spikes to FULL worth, even with a same-card copy in play. A JUST-benched base (ep83686860 f18: two
    Dreepy placed this turn) is NOT eligible — no deploy-now, the card stays sheddable."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    from common.card_worth import ROLE_TIER
    dx = _build_pilot("dragapult_ex")[0]
    DREEPY, DRAKLOAK = 119, 120
    elig = {"active": [{"id": DREEPY, "appearThisTurn": False}], "bench": [], "hand": [{"id": DRAKLOAK}]}
    assert DRAKLOAK in dx._deploy_now_ids(elig, turn=10)          # eligible base active -> deploy-now
    just_benched = {"active": [{"id": 1071}], "hand": [{"id": DRAKLOAK}],
                    "bench": [{"id": DREEPY, "appearThisTurn": True}]}
    assert DRAKLOAK not in dx._deploy_now_ids(just_benched, turn=2)   # base placed this turn -> not eligible
    assert DRAKLOAK not in dx._deploy_now_ids(elig, turn=1)       # turn 1 -> no evolution at all
    # the spike zeros re-access -> keep at FULL worth even with a same-card copy in play
    counts = {DRAKLOAK: 1}
    spike = Board(turn=10, deploy_now_ids=frozenset({DRAKLOAK}), in_play_ids=frozenset({DREEPY, DRAKLOAK}))
    covered = Board(turn=10, in_play_ids=frozenset({DREEPY, DRAKLOAK}))
    assert dx._gate_closing(DRAKLOAK, spike) is True
    assert dx._keep_cost(DRAKLOAK, counts, 40, 6, spike) == ROLE_TIER["win_condition_base"]   # 20, spiked
    assert dx._keep_cost(DRAKLOAK, counts, 40, 6, covered) < ROLE_TIER["win_condition_base"]  # re-access discount


@pytest.mark.req("REQ-GATE-0003")
def test_pressure_gate_spikes_the_doomed_successor_and_the_clutch_answers():
    """The fold of `hold-successor-when-doomed` (ep83037962 f49): under a DOOMED Active, the held
    SUCCESSOR (a win-condition with its Line pre-evolution in play — the next attacker, not a
    redundant duplicate) and the clutch answers (`clutch_heal` / `switch` Trainers) charge their
    FULL role worth — the closure's re-access discount is a probabilistic redraw the doom deadline
    cannot bank on. A healthy board keeps the graded discount; a non-answer card (an Energy) never
    spikes; and a successor whose base is provably GONE stays dead (the evolution gate outranks —
    dead is dead, doom or not)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    from common.card_worth import ROLE_TIER, TAG_TIER
    ms = _build_pilot("mega_starmie")[0]
    staryu = next(c for c in set(ms.deck)
                  if getattr(ms.stats.get(c), "name", None) == "Staryu")
    counts = {1031: 1, 1121: 4, 1145: 2, staryu: 3}     # successor + Ultra Ball + Mega Signal + bases
    pool, draws = 40, 6
    healthy = Board()
    doomed = Board(active_doomed=True, line_preevo_in_play=True,
                   in_play_ids=frozenset({staryu}))
    graded = ms._keep_cost(1031, counts, pool, draws, healthy)
    assert 0 < graded < ROLE_TIER["win_condition"]       # healthy: the closure discount applies
    assert ms._keep_cost(1031, counts, pool, draws, doomed) == ROLE_TIER["win_condition"]
    # the clutch heal spikes to its full TAG_TIER worth under doom
    heal_counts = {1229: 2, 1121: 4}
    assert ms._keep_cost(1229, heal_counts, pool, draws, healthy) < TAG_TIER["clutch_heal"]
    assert ms._keep_cost(1229, heal_counts, pool, draws, doomed) == TAG_TIER["clutch_heal"]
    # a non-answer card (typed Basic Energy) is untouched by the doom
    e = next(c for c in set(ms.deck)
             if getattr(ms.stats.get(c), "is_typed_basic_energy", False))
    assert (ms._keep_cost(e, {e: 8}, pool, draws, doomed)
            == ms._keep_cost(e, {e: 8}, pool, draws, healthy))
    # dead is dead: no Staryu anywhere -> the evolution gate zeroes the successor, doom or not
    dead = Board(active_doomed=True, line_preevo_in_play=False)
    assert ms._keep_cost(1031, {1031: 1, 1121: 4}, pool, draws, dead) == 0.0


@pytest.mark.req("REQ-GATE-0004")
def test_quota_window_widens_with_copy_rank_and_spent_quota():
    """The quota gate's primitive (spec Round 8 §2: resource quotas are gates — the k-th held copy
    of a once-per-turn card has deadline k−1 turns, so every intervening turn adds its natural draw
    of re-access before that copy is needed). Rank 1 with the quota live keeps the plain window;
    a spent quota shifts every rank one turn further out."""
    assert gate_library.quota_window(6, 1) == 6                  # the first copy: needed now
    assert gate_library.quota_window(6, 2) == 7                  # 2nd copy: one turn of draws first
    assert gate_library.quota_window(6, 3) == 8
    assert gate_library.quota_window(6, 1, quota_spent=True) == 7    # attach/slot already used
    assert gate_library.quota_window(6, 3, quota_spent=True) == 9
    assert gate_library.quota_window(6, 0) == 6                  # a degenerate rank never narrows


@pytest.mark.req("REQ-GATE-0004")
def test_hand_keep_prices_quota_duplicates_by_their_deadline_rank():
    """The quota gate wired into `_hand_keep`: duplicate copies of a ONCE-PER-TURN card (Energy —
    1 manual attach; Supporter — 1 per turn, rules.md §3) charge by RANK — the k-th copy's
    re-access window widens by its k−1 turns of natural draws, so the 3rd held Energy is cheaper to
    shuffle than the 1st (the spec's own derivation). A lone copy with the quota live is unchanged;
    a spent quota (`energy_attached`; a Supporter refresh being the played card) widens every rank;
    non-quota duplicates (a Pokémon) are untouched."""
    import sys
    from math import isclose
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    ms = _build_pilot("mega_starmie")[0]
    e = next(c for c in set(ms.deck)
             if getattr(ms.stats.get(c), "is_typed_basic_energy", False))
    counts, pool, draws = {e: 8}, 40, 6
    live = Board()
    # a lone held copy with the quota live: the plain window — unchanged by the gate
    assert isclose(ms._hand_keep([e], None, counts, pool, draws, live),
                   ms._keep_cost(e, counts, pool, draws, live))
    # three held copies: rank-widened windows -> strictly cheaper than three uniform charges
    uniform3 = 3 * ms._keep_cost(e, counts, pool, draws, live, shuffled_copies=3)
    ranked3 = ms._hand_keep([e, e, e], None, counts, pool, draws, live)
    expect3 = sum(ms._keep_cost(e, counts, pool, gate_library.quota_window(draws, j), live,
                                shuffled_copies=3) for j in (1, 2, 3))
    assert isclose(ranked3, expect3)
    assert 0 < ranked3 < uniform3
    # a spent attach quota widens every rank -> cheaper still
    spent = Board(energy_attached=True)
    assert ms._hand_keep([e, e, e], None, counts, pool, draws, spent) < ranked3
    # the SUPPORTER leg: playing a Supporter refresh spends the slot, so even a lone held
    # worth-carrying Supporter (Wally's, `clutch_heal` 20) shifts a turn out
    wallys = 1229
    sup_counts = {wallys: 2}
    played_sup = 1223                                            # Harlequin, a Supporter refresh
    one = ms._hand_keep([wallys], None, sup_counts, pool, draws, live)
    one_after_sup = ms._hand_keep([wallys, played_sup], played_sup, sup_counts, pool, draws, live)
    assert 0 < one_after_sup < one
    # non-quota duplicates (the wincon, a Pokémon) keep the uniform marginal price
    w_counts = {1031: 1, 1121: 4}
    assert isclose(ms._hand_keep([1031, 1031], None, w_counts, pool, draws, live),
                   2 * ms._keep_cost(1031, w_counts, pool, draws, live, shuffled_copies=2))


@pytest.mark.req("REQ-GATE-0002")
def test_pilot_deploy_odds_collapses_a_dead_searcher_and_recycler():
    """The Pilot resolver (`planner._deploy_odds`) mirrors the play-side rungs' SOUND predicates:
    a Buddy-Buddy Poffin whose whole deck whiff-set sits in `Board.deck_empty_ids` prices 0
    (`dont-search-an-empty-deck`'s premise), a Night Stretcher on an all-dead recycle pool prices 0
    (`dont-recycle-the-dead`'s premise) — and both keep FULL worth when any target is live. The gate
    then collapses `_keep_cost` so the dead fetcher no longer props up the refresh SHED
    (the ep83457493 f31 pin: shed the dead hand into Harlequin)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    ms = _build_pilot("mega_starmie")[0]
    poffin, stretcher = 1086, 1097
    fetch_set = ms._search_deck_set(poffin)
    assert fetch_set, "Poffin must have a deck whiff-set for this test to mean anything"
    live, counts = Board(), {cid: 1 for cid in fetch_set}
    dead_search = Board(deck_empty_ids=frozenset(fetch_set))
    assert ms._deploy_odds(poffin, live, counts) == 1.0
    assert ms._deploy_odds(poffin, dead_search, counts) == 0.0
    assert ms._keep_cost(poffin, counts, 40, 6, dead_search) == 0.0     # the SHED sees a free shed
    assert ms._keep_cost(poffin, counts, 40, 6, live) > 0.0
    dead_pool = Board(recycle_dead_only=True)
    assert ms._deploy_odds(stretcher, dead_pool, counts) == 0.0
    assert ms._deploy_odds(stretcher, Board(), counts) == 1.0
