"""Opponent Briefs compile eagerly into the immutable knowledge base."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.cards.pokemon_roles import POKEMON_ROLES
from common.opponent import OpponentKnowledgeBase
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.provider import EngineCardStatProvider


_BRIEFS_DIR = Path(__file__).resolve().parents[2] / "src" / "common" / "scouting" / "briefs"


def _write_brief(directory, slug="sample", **values):
    payload = {
        "slug": slug, "covers": values.get("covers", ["Sample"]),
        "traits": values.get("traits", {}), "pokemon": values.get("pokemon", []),
        "key_cards": values.get("key_cards", []),
    }
    (directory / f"{slug}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_loader_reads_typed_traits_and_strict_mode_rejects_bad_artifacts(tmp_path):
    _write_brief(tmp_path, traits={"tempo": "fast"})
    loaded = load_briefs(tmp_path, strict=True)

    assert loaded[0].traits == {"tempo": "fast"}
    (tmp_path / "broken.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_briefs(tmp_path, strict=True)
    assert [brief.slug for brief in load_briefs(tmp_path)] == ["sample"]


def test_strict_loader_rejects_schema_drift(tmp_path):
    _write_brief(tmp_path)
    path = tmp_path / "sample.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unknown"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="top-level schema"):
        load_briefs(tmp_path, strict=True)


def test_knowledge_rejects_duplicate_routes_even_outside_the_artifact():
    provider = EngineCardStatProvider()
    provider.warm()
    first = load_briefs(strict=True)[0]
    duplicate = type(first)(
        "duplicate", "Duplicate", [first.covers[0]], {}, [], [])

    with pytest.raises(ValueError, match="multiple profiles"):
        OpponentKnowledgeBase.compile(load_artifact(strict=True), (first, duplicate), provider)


def test_shipped_briefs_have_unique_routes_and_only_canonical_roles():
    seen = {}
    provider = EngineCardStatProvider()
    provider.warm()
    for brief in load_briefs(strict=True):
        for archetype in brief.covers:
            key = archetype.replace("’", "'")
            assert key not in seen, f"{archetype!r} covered by {seen.get(key)!r} and {brief.slug!r}"
            seen[key] = brief.slug
        for entry in brief.pokemon:
            assert provider.ids_for_name(entry["card"]), (
                f"{brief.slug}: unresolved Pokemon {entry['card']!r}")
            assert set(entry["roles"]) <= set(POKEMON_ROLES)


def test_every_shipped_profile_compiles_against_card_facts_and_artifact():
    provider = EngineCardStatProvider()
    provider.warm()
    knowledge = OpponentKnowledgeBase.compile(
        load_artifact(strict=True), load_briefs(strict=True), provider)

    assert set(knowledge.profiles) == set(knowledge.priors)
    assert knowledge.identity


def test_briefs_cover_every_representative_build_pokemon():
    provider = EngineCardStatProvider()
    provider.warm()
    artifact = load_artifact(strict=True)
    for brief in load_briefs(strict=True):
        represented = set().union(
            *(provider.ids_for_name(row["card"]) for row in brief.pokemon))
        expected = set()
        for cover in brief.covers:
            for card_id in (artifact.dossiers.get(cover) or {}).get("representative_build") or ():
                stat = provider.get(int(card_id))
                if stat is not None and stat.is_pokemon:
                    expected.add(int(card_id))
        assert expected <= represented, f"{brief.slug}: missing {sorted(expected - represented)}"


def test_shipped_briefs_keep_bounded_review_layout():
    for path in _BRIEFS_DIR.glob("*.json"):
        raw = path.read_bytes()
        assert max(len(line) for line in raw.splitlines()) <= 120, path.name
