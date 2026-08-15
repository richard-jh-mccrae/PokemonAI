"""Offline compiler: synthetic meta -> shipped artifact dict (docs/scouting.md)."""
import pytest

from meta_tracker.compile_scouting import compile_artifact

NOW = "2026-06-23T00:00:00"

RIOLU, LUCARIO, MEGA, SOLROCK = 677, 679, 678, 676
CARDS = {
    RIOLU:   {"name": "Riolu", "category": "pokemon", "stage": "basic",
              "maxDamage": 0, "ex": False, "megaEx": False, "evolvesFrom": None, "energy": "fighting"},
    LUCARIO: {"name": "Lucario", "category": "pokemon", "stage": "stage1",
              "maxDamage": 0, "ex": False, "megaEx": False, "evolvesFrom": "Riolu", "energy": "fighting"},
    MEGA:    {"name": "Mega Lucario ex", "category": "pokemon", "stage": "stage2",
              "maxDamage": 270, "ex": True, "megaEx": True, "evolvesFrom": "Lucario", "energy": "fighting"},
    SOLROCK: {"name": "Solrock", "category": "pokemon", "stage": "basic",
              "maxDamage": 70, "ex": False, "megaEx": False, "evolvesFrom": None, "energy": "fighting"},
}


def _ep(arch0, deck0, arch1, deck1, *, band="Mid", end_time="2026-06-20T00:00:00"):
    return {"arch0": arch0, "deck0": deck0, "arch1": arch1, "deck1": deck1,
            "band": band, "end_time": end_time}


@pytest.mark.req("REQ-SCOUT-0007")
def test_priors_reflect_archetype_frequency():
    eps = [
        _ep("A", [1], "A", [1]),   # A appears 4x, B 2x across these
        _ep("A", [1], "B", [2]),
        _ep("B", [2], "A", [1]),
    ]
    art = compile_artifact(eps, cards={}, now=NOW)

    assert art["priors"]["A"] > art["priors"]["B"]
    assert abs(sum(art["priors"].values()) - 1.0) < 1e-9


@pytest.mark.req("REQ-SCOUT-0007")
def test_card_inclusion_and_background():
    SIG, COMMON = 676, 200
    eps = [
        _ep("Lucario", [SIG, COMMON], "Other", [COMMON]),
        _ep("Lucario", [SIG, COMMON], "Other", [COMMON]),
    ]
    art = compile_artifact(eps, cards={}, now=NOW)

    incl = art["dossiers"]["Lucario"]["card_inclusion"]
    assert incl[SIG] == pytest.approx(1.0)                       # in every Lucario deck
    assert art["background"][COMMON] > art["background"][SIG]    # COMMON everywhere


@pytest.mark.req("REQ-SCOUT-0001")
def test_signatures_are_high_lift_cards():
    SIG, COMMON = 676, 200
    eps = [
        _ep("Lucario", [SIG, COMMON], "Other", [COMMON]),
        _ep("Lucario", [SIG, COMMON], "Other", [COMMON]),
        _ep("Other", [COMMON], "Other", [COMMON]),
    ]
    art = compile_artifact(eps, cards={}, now=NOW)

    sigs = [s["cardId"] for s in art["dossiers"]["Lucario"]["signatures"]]
    assert SIG in sigs        # near-exclusive to Lucario -> high lift
    assert COMMON not in sigs # ubiquitous -> lift ~1


@pytest.mark.req("REQ-SCOUT-0005")
def test_representative_build_is_most_common_decklist():
    A1, A2 = [1, 1, 2], [1, 3, 3]
    eps = [_ep("A", A1, "A", A1), _ep("A", A1, "A", A2)]   # A1 x3, A2 x1

    art = compile_artifact(eps, cards={}, now=NOW)

    assert sorted(art["dossiers"]["A"]["representative_build"]) == sorted(A1)


@pytest.mark.req("REQ-SCOUT-0007")
def test_recency_decay_favors_recent_builds():
    OLD, RECENT = "2026-01-01T00:00:00", "2026-06-22T00:00:00"
    A_OLD, A_NEW = [1, 2], [1, 3]
    eps = ([_ep("A", A_OLD, "A", A_OLD, end_time=OLD)] * 3      # 6 old instances
           + [_ep("A", A_NEW, "A", A_NEW, end_time=RECENT)] * 2)  # 4 recent instances

    art = compile_artifact(eps, cards={}, now=NOW, half_life_days=21.0)

    # rarer raw, but recent build dominates after decay
    assert sorted(art["dossiers"]["A"]["representative_build"]) == sorted(A_NEW)


@pytest.mark.req("REQ-SCOUT-0004")
def test_dossier_has_evolution_lines_and_roles():
    build = [RIOLU, LUCARIO, MEGA, SOLROCK]
    art = compile_artifact([_ep("Lucario", build, "Lucario", build)], CARDS, now=NOW)

    doss = art["dossiers"]["Lucario"]
    assert any(line[-1] == MEGA and RIOLU in line for line in doss["evolution_lines"])
    assert MEGA in {t["cardId"] for t in doss["threats"]}          # big attacker
    roles = {t["cardId"]: t["role"] for t in doss["targets"]}
    assert roles.get(MEGA) == "primary_attacker"                    # ex/Mega
    assert roles.get(RIOLU) == "fragile_preevo"                    # pre-evo of win-con


@pytest.mark.req("REQ-SCOUT-0007")
def test_refuses_below_episode_floor():
    with pytest.raises(ValueError):
        compile_artifact([_ep("A", [1], "A", [1])], cards={}, now=NOW, min_episodes=5)


@pytest.mark.req("REQ-SCOUT-0007")
def test_band_balanced_prior_ignores_oversampling():
    # "Low" floods with A; "Elite" has only B. Raw pooling -> A ~0.95; balanced -> ~0.5 each.
    eps = [_ep("A", [1], "A", [1], band="Low")] * 10 + [_ep("B", [2], "B", [2], band="Elite")]

    art = compile_artifact(eps, cards={}, now=NOW)

    assert art["priors"]["A"] == pytest.approx(art["priors"]["B"], abs=0.1)


# --- Matchup intelligence (REQ-SCOUT-0009) ---------------------------------------

def _epw(arch0, arch1, winner_index, *, band="Mid", end_time="2026-06-20T00:00:00"):
    """An episode with a result (``winner_index`` 0/1, or None for a draw)."""
    return {"arch0": arch0, "deck0": [1], "arch1": arch1, "deck1": [2],
            "band": band, "end_time": end_time, "winner_index": winner_index}


@pytest.mark.req("REQ-SCOUT-0009")
def test_matchup_winrate_is_directional_and_symmetric_in_n():
    eps = [_epw("A", "B", 0)] * 5            # A beats B every decisive game
    art = compile_artifact(eps, cards={}, now=NOW)

    a, b = art["dossiers"]["A"], art["dossiers"]["B"]
    assert a["matchups"]["B"]["win_rate"] > 0.5 > b["matchups"]["A"]["win_rate"]
    assert a["matchups"]["B"]["n"] == pytest.approx(b["matchups"]["A"]["n"])  # same games count


@pytest.mark.req("REQ-SCOUT-0009")
def test_draws_excluded_from_winrate_and_count():
    # Symmetric 1-1 record + 5 draws: marginal stays exactly 0.5, draws add no weight.
    eps = [_epw("A", "B", 0), _epw("A", "B", 1)] + [_epw("A", "B", None)] * 5
    art = compile_artifact(eps, cards={}, now=NOW)

    a, b = art["dossiers"]["A"], art["dossiers"]["B"]
    assert a["win_rate"] == pytest.approx(0.5)
    assert a["win_n"] == pytest.approx(b["win_n"])
    assert a["win_n"] > 0                       # the two decisive games counted
    assert a["win_n"] < 2.0                      # recency-decayed, no draw weight


@pytest.mark.req("REQ-SCOUT-0009")
def test_sparse_cell_shrinks_toward_marginal_not_raw():
    # A ~50% overall; one lucky decisive win vs C must not read as 100%.
    eps = [_epw("A", "B", 0), _epw("A", "B", 1), _epw("A", "C", 0)]
    art = compile_artifact(eps, cards={}, now=NOW)

    assert 0.5 < art["dossiers"]["A"]["matchups"]["C"]["win_rate"] < 1.0


@pytest.mark.req("REQ-SCOUT-0009")
def test_recent_results_outweigh_old_ones():
    OLD, RECENT = "2026-01-01T00:00:00", "2026-06-23T00:00:00"
    eps = ([_epw("A", "B", 1, end_time=OLD)] * 5      # A lost a lot, long ago
           + [_epw("A", "B", 0, end_time=RECENT)] * 5)  # A wins lately
    art = compile_artifact(eps, cards={}, now=NOW, half_life_days=21.0)

    assert art["dossiers"]["A"]["win_rate"] > 0.5


@pytest.mark.req("REQ-SCOUT-0009")
def test_resultless_meta_leaves_neutral_winrate():
    # No winner_index at all (legacy episode shape) -> neutral defaults, no crash.
    art = compile_artifact([_ep("A", [1], "B", [2])], cards={}, now=NOW)

    assert art["dossiers"]["A"]["win_rate"] == 0.5
    assert art["dossiers"]["A"]["win_n"] == 0.0
    assert art["dossiers"]["A"]["matchups"] == {}
