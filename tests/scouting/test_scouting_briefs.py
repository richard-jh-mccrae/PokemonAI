"""Brief-consumer runtime: load Matchup Briefs + match one to the Read (ADR-0027).

Offline, synthetic briefs. The γ-gated consumers are the ADR-0038 Tactical levers (test_posture_read).
"""
import json
from types import SimpleNamespace

import pytest

from common.scouting.briefs import (
    Brief, load_briefs, match_brief, resolve_brief_cards, resolve_scouted_role_worth,
)
from common.scouting.matchup_plan import build_matchup_plan
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read


def _write_brief(d, slug, covers, **extra):
    brief = {"slug": slug, "covers": covers, "wincon": extra.get("wincon", {"line": ["Base"], "plan": "attack"}),
             "opponent_properties": extra.get("opponent_properties", {}),
             "pokemon": extra.get("pokemon", []), "key_cards": extra.get("key_cards", [])}
    (d / f"{slug}.json").write_text(json.dumps(brief), encoding="utf-8")


def _read(*candidates):
    """Candidates are (archetype, posterior) pairs, highest first."""
    return Read(candidates=list(candidates))


def test_load_briefs_reads_a_well_formed_brief(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam", "Alakazam / Frillish"], label="Alakazam")
    briefs = load_briefs(tmp_path)
    assert len(briefs) == 1
    assert briefs[0].slug == "alakazam"
    assert "Alakazam / Frillish" in briefs[0].covers


def test_load_briefs_is_fail_safe(tmp_path):
    _write_brief(tmp_path, "good", ["Good"])
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "noslug.json").write_text('{"covers": ["X"]}', encoding="utf-8")   # missing slug
    briefs = load_briefs(tmp_path)
    assert [b.slug for b in briefs] == ["good"]
    assert load_briefs(tmp_path / "nope") == []


def test_match_brief_routes_top_candidate_via_covers(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam", "Alakazam / Frillish"])
    _write_brief(tmp_path, "hariyama", ["Hariyama / Mega Lucario ex"])
    briefs = load_briefs(tmp_path)
    # the top candidate is a VARIANT string, not the label
    m = match_brief(briefs, _read(("Alakazam / Frillish", 0.7), ("Hariyama / Mega Lucario ex", 0.2)))
    assert m is not None and m.slug == "alakazam"


def test_match_brief_none_when_unrecognized(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam"])
    briefs = load_briefs(tmp_path)
    assert match_brief(briefs, _read(("Some Off-Meta Deck", 0.3))) is None   # no covering Brief
    assert match_brief(briefs, _read()) is None                              # no candidates
    assert match_brief(briefs, None) is None                                 # no Read


def _ml_brief(**extra):
    return Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                 pokemon=extra.get("pokemon", [
                     {"card": "Mega Lucario ex", "roles": ["wincon", "primary_attacker"]},
                     {"card": "Riolu", "roles": ["wincon_base"]},
                 ]))


def test_resolve_brief_cards_maps_names_to_ids_and_roles():
    name_ids = {"Mega Lucario ex": {678}, "Riolu": {677}}
    threat_ids, target_roles = resolve_brief_cards(_ml_brief(), lambda n: name_ids.get(n, ()))
    assert threat_ids == frozenset({677, 678})
    assert target_roles == {678: "prize_liability", 677: "fragile_preevo"}


def test_resolve_brief_cards_skips_unresolvable_names():
    threat_ids, target_roles = resolve_brief_cards(
        _ml_brief(pokemon=[{"card": "Mega Lucario ex", "roles": ["wincon"]},
                            {"card": "Ghost Card", "roles": ["support"]}]),
        lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "prize_liability"}  # unresolved support is dropped


def test_resolve_brief_cards_maps_a_name_to_all_its_ids():
    _, target_roles = resolve_brief_cards(
        _ml_brief(pokemon=[{"card": "Riolu", "roles": ["wincon_base"]}]),
        lambda n: {"Riolu": {677, 6771}}.get(n, ()))
    assert target_roles == {677: "fragile_preevo", 6771: "fragile_preevo"}


def test_resolve_brief_cards_lists_a_card_that_is_both_threat_and_target():
    brief = _ml_brief(pokemon=[{"card": "Mega Lucario ex", "roles": ["wincon", "primary_attacker"]}])
    threat_ids, target_roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "prize_liability"}


def test_bellman_role_worth_uses_authored_brief_roles_and_payoff_prizes():
    brief = _ml_brief()
    brief.wincon = {"line": ["Riolu", "Mega Lucario ex"]}

    class Stats:
        @staticmethod
        def ids_for_name(name):
            return {"Riolu": {677}, "Mega Lucario ex": {678}}.get(name, ())

        @staticmethod
        def get(card_id):
            return SimpleNamespace(prize_value=3 if card_id == 678 else 1, stage="basic")

    worth = resolve_scouted_role_worth(
        _read(("Mega Lucario ex", 1.0)), SimpleNamespace(dossiers={}), Stats(), briefs=(brief,))

    assert worth[677] > worth[678]


def test_bellman_role_worth_does_not_promote_every_dossier_line_to_wincon():
    artifact = SimpleNamespace(dossiers={"Deck": {
        "targets": ({"cardId": 1, "role": "fragile_preevo"},
                    {"cardId": 2, "role": "engine"}),
        "evolution_lines": ((1, 3), (2, 4)),
    }})
    stats = SimpleNamespace(get=lambda _card_id: SimpleNamespace(stage="basic"))

    worth = resolve_scouted_role_worth(_read(("Deck", 1.0)), artifact, stats)

    assert worth[1] > worth[2]


def test_shipped_briefs_have_no_covers_collision():
    """REQ-BRIEF-0001: match_brief returns the alphabetically-first covering Brief, so an overlapping
    `covers` string would misroute SILENTLY."""
    seen: dict[str, str] = {}
    for brief in load_briefs():                    # the real src/common/scouting/briefs/ dir
        for arch in brief.covers:
            assert arch not in seen, (
                f"archetype {arch!r} covered by both {seen[arch]!r} and {brief.slug!r} — "
                f"every archetype string must route to exactly ONE Brief")
            seen[arch] = brief.slug


@pytest.mark.req("REQ-BRIEF-0003")
def test_dragapult_brief_ranks_its_wincon_above_its_support_exes():
    """The support ex's are all 2-prize bodies too, so without this the gust drags up a support body
    over the one whose loss ends the game. `_snipe_tera_veto` is what lets the wincon carry a role."""
    prov = EngineCardStatProvider()
    brief = next(b for b in load_briefs() if b.slug == "dragapult_ex")
    _, roles = resolve_brief_cards(brief, prov.ids_for_name)
    plan = build_matchup_plan(brief_roles=roles, gamma=1.0)

    def _pri(name):
        return max(plan.priority(i) for i in prov.ids_for_name(name))

    wincon = _pri("Dragapult ex")
    assert wincon > 0, "the Dragapult ex WINCON must carry a target role (it had none)"
    for support in ("Fezandipiti ex", "Latias ex", "Meowth ex"):
        assert wincon > _pri(support), (
            f"Dragapult ex (the win-condition) must out-rank the support ex {support!r} — all are "
            f"2-prize bodies, so the gust would otherwise drag up a support body over the wincon")


def _ancestor_names(prov, cid: int) -> set[str]:
    names: set[str] = set()
    stat = prov.get(cid)
    name = getattr(stat, "evolvesFrom", None) if stat else None
    while name and name not in names:
        names.add(name)
        nxt = None
        for i in (prov.ids_for_name(name) or ()):
            s = prov.get(i)
            if s and getattr(s, "evolvesFrom", None):
                nxt = s.evolvesFrom
                break
        name = nxt
    return names


@pytest.mark.req("REQ-BRIEF-0002")
def test_shipped_briefs_never_neutralize_a_wincon_line_payoff():
    """ADR-0051: `engine` is priority 0 in `build_matchup_plan`'s top last-write-wins tier, so it is
    an ACTIVE suppressor. OMITTING a payoff from `targets` stays legitimate and is NOT pinned here."""
    prov = EngineCardStatProvider()
    for brief in load_briefs():
        _, target_roles = resolve_brief_cards(brief, prov.ids_for_name)
        payoff = brief.wincon.get("line", [])[-1:]
        for name in payoff:
            ids = prov.ids_for_name(name) or ()
            assert any(target_roles.get(cid) == "prize_liability" for cid in ids), (
                f"{brief.slug}: wincon payoff {name!r} must resolve to prize_liability")


def test_compact_roles_supply_threat_and_target_readers():
    """One doctrine source drives denial (threat) plus snipe/gust (target priority)."""
    brief = _ml_brief(pokemon=[
        {"card": "Mega Lucario ex", "roles": ["wincon", "primary_attacker"]},
        {"card": "Riolu", "roles": ["wincon_base"]},
    ])
    threats, roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}, "Riolu": {677}}.get(n, ()))
    plan = build_matchup_plan(brief_roles=roles, gamma=1.0)
    assert threats == frozenset({677, 678})            # Wincon stages are Brief threat inputs
    assert plan.priority(677) > 0 and plan.priority(678) > plan.priority(677)  # snipe + gust
