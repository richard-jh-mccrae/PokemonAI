"""Brief-consumer runtime: load Matchup Briefs + match one to the Read (ADR-0027).

Offline, synthetic briefs. The γ-gated consumers are the ADR-0038 Tactical levers (test_posture_read).
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.card_worth import role_value
from common.cards import CardFunctions
from common.scouting.pokemon_roles import general_pokemon_roles
from common.scouting.artifact import load_artifact
from common.scouting.briefs import (
    Brief, load_briefs, match_brief, resolve_brief_cards, resolve_scouted_role_worth,
)
from common.scouting.matchup_plan import build_matchup_plan
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read


_BRIEFS_DIR = Path(__file__).resolve().parents[2] / "src" / "common" / "scouting" / "briefs"


@pytest.mark.parametrize(("name", "purpose"), (
    ("Dunsparce", "draw_engine"),
    ("Dudunsparce", "draw_engine"),
    ("Drakloak", "draw_engine"),
    ("Mega Kangaskhan ex", "draw_engine"),
    ("Latias ex", "retreat_assist"),
    ("Budew", "item_locker"),
    ("Meowth ex", "search_engine"),
    ("Fezandipiti ex", "draw_engine"),
))
def test_generic_support_pokemon_roles_preserve_their_purpose(name, purpose):
    provider = EngineCardStatProvider()
    functions = CardFunctions.load()
    ids = provider.ids_for_name(name)
    roles = general_pokemon_roles(ids, provider, functions)
    assert ids and all(
        {"support_pokemon", purpose} <= set(roles.get(card_id, ())) for card_id in ids)


def _write_brief(d, slug, covers, **extra):
    brief = {"slug": slug, "covers": covers, "opponent_properties": extra.get("opponent_properties", {}),
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
    assert not hasattr(briefs[0], "strategies")


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
                     {"card": "Mega Lucario ex", "roles": ["primary_attacker"]},
                     {"card": "Hariyama", "roles": ["backup_attacker"]},
                 ]))


def test_resolve_brief_cards_maps_names_to_ids_and_roles():
    name_ids = {"Mega Lucario ex": {678}, "Hariyama": {679}}
    threat_ids, target_roles = resolve_brief_cards(_ml_brief(), lambda n: name_ids.get(n, ()))
    assert threat_ids == frozenset({678, 679})
    assert target_roles == {678: "primary_attacker", 679: "backup_attacker"}


def test_resolve_brief_cards_skips_unresolvable_names():
    threat_ids, target_roles = resolve_brief_cards(
        _ml_brief(pokemon=[{"card": "Mega Lucario ex", "roles": ["primary_attacker"]},
                            {"card": "Ghost Card", "roles": ["support"]}]),
        lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "primary_attacker"}  # unresolved support is dropped


def test_resolve_brief_cards_maps_a_name_to_all_its_ids():
    _, target_roles = resolve_brief_cards(
        _ml_brief(pokemon=[{"card": "Hariyama", "roles": ["backup_attacker"]}]),
        lambda n: {"Hariyama": {679, 6791}}.get(n, ()))
    assert target_roles == {679: "backup_attacker", 6791: "backup_attacker"}


def test_resolve_brief_cards_lists_a_card_that_is_both_threat_and_target():
    brief = _ml_brief(pokemon=[{"card": "Mega Lucario ex", "roles": ["primary_attacker"]}])
    threat_ids, target_roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "primary_attacker"}


def test_bellman_role_worth_expands_primary_attacker_to_its_ancestors():
    brief = _ml_brief()

    class Stats:
        @staticmethod
        def ids_for_name(name):
            return {"Riolu": {677}, "Mega Lucario ex": {678}}.get(name, ())

        @staticmethod
        def get(card_id):
            return SimpleNamespace(
                prize_value=3 if card_id == 678 else 1,
                stage="basic" if card_id == 677 else "stage1",
                evolvesFrom="Riolu" if card_id == 678 else None)

        @staticmethod
        def forward_card_ids(card_id):
            return {678} if card_id == 677 else set()

    worth = resolve_scouted_role_worth(
        _read(("Mega Lucario ex", 1.0)), SimpleNamespace(dossiers={}), Stats(), briefs=(brief,))

    assert worth[677] == worth[678] > 0          # line_decay defaults to the flat 1.0 stamp


def test_bellman_role_worth_ranks_a_line_by_the_evolution_steps_still_owed():
    """A Brief names ONE primary attacker and the stamp covers its whole line, so at line_decay=1.0
    the Basic prices exactly like the body about to become the win condition and a snipe has no
    reason to prefer either. Frame fa978d4e6fe4: it sniped a spare Marnie's Impidimp over the lone
    Marnie's Morgrem one evolution short of Marnie's Grimmsnarl ex."""
    brief = _ml_brief()

    class Stats:
        @staticmethod
        def ids_for_name(name):
            return {"Riolu": {677}, "Mega Lucario ex": {678}}.get(name, ())

        @staticmethod
        def get(card_id):
            return SimpleNamespace(
                prize_value=3 if card_id == 678 else 1,
                stage="basic" if card_id == 677 else "stage1",
                evolvesFrom="Riolu" if card_id == 678 else None)

        @staticmethod
        def forward_card_ids(card_id):
            return {678} if card_id == 677 else set()

    worth = resolve_scouted_role_worth(
        _read(("Mega Lucario ex", 1.0)), SimpleNamespace(dossiers={}), Stats(), briefs=(brief,),
        line_decay=0.8)

    assert worth[678] > worth[677] > 0
    assert worth[677] == pytest.approx(worth[678] * 0.8)


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


def test_shipped_briefs_are_readable_crlf_json_with_bounded_lines():
    """Briefs are reviewed directly, so preserve their intentional on-disk layout."""
    for path in _BRIEFS_DIR.glob("*.json"):
        raw = path.read_bytes()
        assert b"\n" not in raw.replace(b"\r\n", b""), f"{path.name}: expected CRLF"
        assert max(len(line) for line in raw.split(b"\r\n")) <= 120, f"{path.name}: line over 120 columns"


def test_every_shipped_brief_pokemon_resolves_to_a_role():
    provider = EngineCardStatProvider()
    functions = CardFunctions.load()
    for brief in load_briefs():
        _, resolved = resolve_brief_cards(
            brief, provider.ids_for_name, stat_for_id=provider.get,
            forward_ids=provider.forward_card_ids, functions=functions)
        for entry in brief.pokemon:
            ids = provider.ids_for_name(entry["card"])
            assert ids and all(card_id in resolved for card_id in ids), (
                f"{brief.slug}: {entry['card']} has no resolved Role")
            assert all(role_value((resolved[card_id],)) > 0 for card_id in ids), (
                f"{brief.slug}: {entry['card']} has a Role with no Bellman Worth")


def test_briefs_list_every_representative_build_pokemon():
    provider = EngineCardStatProvider()
    artifact = load_artifact()
    for brief in load_briefs():
        represented = set().union(*(provider.ids_for_name(row["card"]) for row in brief.pokemon))
        expected = set()
        for cover in brief.covers:
            for card_id in (artifact.dossiers.get(cover) or {}).get("representative_build") or ():
                stat = provider.get(int(card_id))
                if stat is not None and stat.is_pokemon:
                    expected.add(int(card_id))
        assert expected <= represented, f"{brief.slug}: missing Pokémon ids {sorted(expected - represented)}"


@pytest.mark.req("REQ-BRIEF-0003")
def test_dragapult_brief_ranks_its_primary_attacker_above_its_support_exes():
    """The support ex's are all 2-prize bodies too, so without this the gust drags up a support body
    over the one whose loss ends the game. `_snipe_tera_veto` lets the primary carry a role."""
    prov = EngineCardStatProvider()
    brief = next(b for b in load_briefs() if b.slug == "dragapult_ex")
    _, roles = resolve_brief_cards(
        brief, prov.ids_for_name, stat_for_id=prov.get, forward_ids=prov.forward_card_ids)
    plan = build_matchup_plan(brief_roles=roles, gamma=1.0)

    def _pri(name):
        return max(plan.priority(i) for i in prov.ids_for_name(name))

    primary = _pri("Dragapult ex")
    assert primary > 0, "the Dragapult ex primary attacker must carry a target role"
    for support in ("Fezandipiti ex", "Latias ex", "Meowth ex"):
        assert primary > _pri(support), (
            f"Dragapult ex must out-rank the support ex {support!r} — all are 2-prize bodies, so "
            "the gust would otherwise drag up a support body over the primary attacker")


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
def test_shipped_briefs_make_every_primary_attacker_a_primary_attacker():
    """A primary attacker and every earlier evolution are the curated matchup payoff."""
    prov = EngineCardStatProvider()
    for brief in load_briefs():
        _, target_roles = resolve_brief_cards(
            brief, prov.ids_for_name, stat_for_id=prov.get, forward_ids=prov.forward_card_ids)
        primaries = [entry["card"] for entry in brief.pokemon
                     if "primary_attacker" in entry.get("roles", [])]
        assert primaries, f"{brief.slug}: Brief has no primary attacker"
        for name in primaries:
            ids = prov.ids_for_name(name) or ()
            assert any(target_roles.get(cid) == "primary_attacker" for cid in ids), (
                f"{brief.slug}: primary attacker {name!r} must resolve to primary_attacker")
            ancestor_names = set().union(*(_ancestor_names(prov, card_id) for card_id in ids))
            for ancestor_name in ancestor_names:
                assert all(target_roles.get(card_id) == "primary_attacker"
                           for card_id in prov.ids_for_name(ancestor_name)), (
                    f"{brief.slug}: {ancestor_name!r} must inherit primary-attacker priority")


def test_compact_roles_supply_threat_and_target_readers():
    """One doctrine source drives denial (threat) plus snipe/gust (target priority)."""
    brief = _ml_brief(pokemon=[
        {"card": "Mega Lucario ex", "roles": ["primary_attacker"]},
        {"card": "Hariyama", "roles": ["backup_attacker"]},
    ])
    threats, roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}, "Hariyama": {679}}.get(n, ()))
    plan = build_matchup_plan(brief_roles=roles, gamma=1.0)
    assert threats == frozenset({678, 679})
    assert plan.priority(678) > plan.priority(679) > 0


def test_multiple_primary_attackers_are_supported():
    brief = _ml_brief(pokemon=[
        {"card": "Mega Lucario ex", "roles": ["primary_attacker"]},
        {"card": "Hariyama", "roles": ["primary_attacker"]},
    ])
    _, roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}, "Hariyama": {679}}.get(n, ()))
    assert roles == {678: "primary_attacker", 679: "primary_attacker"}


def test_primary_attacker_expands_both_directions_and_overrides_backup_role():
    class _Stat:
        def __init__(self, name, parent=None):
            self.name = name
            self.evolvesFrom = parent

    stats = {
        1: _Stat("Basic"), 2: _Stat("Stage 1", "Basic"), 3: _Stat("Stage 2", "Stage 1"),
        4: _Stat("Sibling Stage 1", "Basic"),
    }
    names = {stat.name: {card_id} for card_id, stat in stats.items()}
    forward = {1: {2, 3, 4}, 2: {3}, 3: set(), 4: set()}
    brief = _ml_brief(pokemon=[
        {"card": "Stage 2", "roles": ["primary_attacker"]},
        {"card": "Basic", "roles": ["backup_attacker"]},
    ])

    threats, roles = resolve_brief_cards(
        brief, lambda name: names.get(name, ()), stat_for_id=stats.get,
        forward_ids=lambda card_id: forward[card_id])

    assert threats == frozenset({1, 2, 3})
    assert roles == {1: "primary_attacker", 2: "primary_attacker", 3: "primary_attacker"}


def test_brief_matching_ignores_apostrophe_typography():
    """The artifact's archetype labels drift between straight and curly apostrophes per set;
    routing must not hinge on typography (49 corpus frames went unmatched over it)."""
    from common.scouting.briefs import Brief, match_brief
    from common.scouting.read import Read

    brief = Brief(slug="hop", label="hop", covers=["Hop's Trevenant / Hop's Snorlax"])
    curly = Read(candidates=[("Hop's Trevenant / Hop\u2019s Snorlax", 0.95)],
                 unknown_mass=0.0, confidence=(0.95, 0.9))
    assert match_brief([brief], curly) is brief
