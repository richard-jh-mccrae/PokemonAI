"""Scout: turn the live observation into a Read (docs/scouting.md)."""
import pytest

from common.scouting.provider import CardStat, DictCardStatProvider
from common.scouting.read import Read
from common.scouting.scout import Scout
from scouting_helpers import (
    KIRLIA, MEGA_LUCARIO, RIOLU, SHARED, SOLROCK, make_obs, tiny_artifact,
)


@pytest.mark.req("REQ-SCOUT-0001")
def test_recognizes_archetype_from_revealed_board():
    scout = Scout(tiny_artifact())
    obs = make_obs(your_index=0, opp_active=RIOLU, opp_bench=[SOLROCK])

    read = scout.observe(obs)

    assert read.candidates[0][0] == "Mega Lucario ex"


@pytest.mark.req("REQ-SCOUT-0006")
def test_resets_state_on_new_match():
    scout = Scout(tiny_artifact())
    # Match 1: strong Mega Lucario ex evidence.
    scout.observe(make_obs(turn=5, opp_bench=[SOLROCK, RIOLU, MEGA_LUCARIO]))
    # Match 2 begins: the turn counter resets and the board shows a Gardevoir engine
    # piece. Without a reset, match 1's Solrock/Riolu would still dominate.
    read = scout.observe(make_obs(turn=1, opp_active=KIRLIA))

    assert read.candidates[0][0] == "Gardevoir ex"


@pytest.mark.req("REQ-SCOUT-0002")
def test_evidence_accumulates_across_decisions():
    art = tiny_artifact()
    persistent = Scout(art)
    persistent.observe(make_obs(turn=2, opp_bench=[SOLROCK]))          # sees the signature
    read_persist = persistent.observe(make_obs(turn=3, opp_bench=[SHARED]))  # signature now off-board

    read_fresh = Scout(art).observe(make_obs(turn=3, opp_bench=[SHARED]))    # only the ambiguous card

    assert (dict(read_persist.candidates)["Mega Lucario ex"]
            > dict(read_fresh.candidates)["Mega Lucario ex"])


@pytest.mark.req("REQ-SCOUT-0006")
def test_observe_never_raises_on_malformed_obs():
    scout = Scout(tiny_artifact())
    assert isinstance(scout.observe({}), Read)
    assert isinstance(scout.observe({"current": {"players": []}}), Read)
    assert isinstance(scout.observe({"current": {"yourIndex": 0, "players": [None, None]}}), Read)


@pytest.mark.req("REQ-SCOUT-0004")
def test_observed_threats_and_targets_from_board():
    provider = DictCardStatProvider({
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=220, megaEx=True, maxDamage=270),
        KIRLIA: CardStat(KIRLIA, name="Kirlia", hp=80, maxDamage=0),
    })
    scout = Scout(tiny_artifact(), provider=provider)

    read = scout.observe(make_obs(opp_active=MEGA_LUCARIO, opp_bench=[KIRLIA]))

    roles = {t.cardId: t.role for t in read.targets}
    assert roles[MEGA_LUCARIO] == "prize_liability"   # ex/Mega = extra prizes
    assert roles[KIRLIA] == "support"                  # can't attack
    threat_ids = {t.cardId for t in read.threats}
    assert MEGA_LUCARIO in threat_ids and KIRLIA not in threat_ids
    assert all(i.seen for i in read.targets + read.threats)


@pytest.mark.req("REQ-SCOUT-0005")
def test_expected_cards_surface_when_confident():
    scout = Scout(tiny_artifact())
    # Strong, unambiguous Mega Lucario ex read.
    read = scout.observe(make_obs(opp_bench=[SOLROCK, MEGA_LUCARIO]))

    expected_ids = [c for c, _ in read.expected_cards]
    assert RIOLU in expected_ids        # in the build, not yet seen
    assert SOLROCK not in expected_ids  # already revealed


@pytest.mark.req("REQ-SCOUT-0005")
def test_evolution_paths_predict_line_top():
    scout = Scout(tiny_artifact())
    read = scout.observe(make_obs(opp_active=RIOLU, opp_bench=[SOLROCK, MEGA_LUCARIO]))

    paths = {p.seen_cardId: p.top_cardId for p in read.evolution_paths}
    assert paths.get(RIOLU) == MEGA_LUCARIO   # that basic becomes the win-condition


@pytest.mark.req("REQ-SCOUT-0004")
def test_predicted_dossier_targets_surface_unseen_when_confident():
    # Recognized Mega Lucario ex (Solrock signature + Mega Lucario), but Riolu is NOT on board. The
    # dossier's fragile_preevo target (Riolu) is surfaced as a PREDICTED target with seen=False.
    read = Scout(tiny_artifact()).observe(make_obs(opp_active=MEGA_LUCARIO, opp_bench=[SOLROCK]))

    riolu = [t for t in read.targets if t.cardId == RIOLU]
    assert riolu, "predicted dossier target was not surfaced"
    assert riolu[0].role == "fragile_preevo"
    assert riolu[0].seen is False


@pytest.mark.req("REQ-SCOUT-0004")
def test_predicted_dossier_role_overrides_stat_default_for_on_board_card():
    # Riolu is on the board AND is the dossier's fragile_preevo target: the archetype-specific role
    # wins over the observed stat default, and seen=True (it's in play).
    read = Scout(tiny_artifact()).observe(make_obs(opp_active=RIOLU, opp_bench=[SOLROCK, MEGA_LUCARIO]))

    riolu = [t for t in read.targets if t.cardId == RIOLU]
    assert riolu and riolu[0].role == "fragile_preevo" and riolu[0].seen is True


@pytest.mark.req("REQ-SCOUT-0004")
def test_no_predicted_intel_below_the_confidence_bar():
    # An ambiguous board (a card shared by both archetypes) stays below the recognition bar, so the
    # Read carries only OBSERVED intel (all seen) — no predicted dossier targets leak in.
    read = Scout(tiny_artifact()).observe(make_obs(opp_bench=[SHARED]))

    assert all(i.seen for i in read.targets + read.threats)
    assert RIOLU not in {t.cardId for t in read.targets}   # the dossier's predicted target is withheld
