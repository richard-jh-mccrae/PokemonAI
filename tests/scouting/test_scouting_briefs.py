"""Brief-consumer runtime: load Matchup Briefs + match one to the Read (ADR-0027).

Offline, synthetic briefs. The bridge (load + match) mirrors artifact.load_artifact +
matchup.matchup_favorability; the γ-gated consumers are the ADR-0038 Tactical levers (test_posture_read).
"""
import json

import pytest

from common.scouting.briefs import Brief, load_briefs, match_brief, resolve_brief_cards
from common.scouting.read import Read


def _write_brief(d, slug, covers, **extra):
    brief = {"slug": slug, "label": extra.get("label", slug), "covers": covers,
             "tempo": extra.get("tempo", "midrange"), "summary": extra.get("summary", ""),
             "opponent_properties": extra.get("opponent_properties", {}),
             "threats": extra.get("threats", []), "targets": extra.get("targets", [])}
    (d / f"{slug}.json").write_text(json.dumps(brief), encoding="utf-8")


def _read(*candidates):
    """A Read whose candidates are (archetype, posterior) pairs, highest first."""
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
    assert [b.slug for b in briefs] == ["good"]                    # bad files skipped, good kept
    assert load_briefs(tmp_path / "nope") == []                   # missing dir -> []


def test_match_brief_routes_top_candidate_via_covers(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam", "Alakazam / Frillish"])
    _write_brief(tmp_path, "hariyama", ["Hariyama / Mega Lucario ex"])
    briefs = load_briefs(tmp_path)
    # top candidate is a VARIANT string (not the label) -> still routes to alakazam Brief
    m = match_brief(briefs, _read(("Alakazam / Frillish", 0.7), ("Hariyama / Mega Lucario ex", 0.2)))
    assert m is not None and m.slug == "alakazam"


def test_match_brief_none_when_unrecognized(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam"])
    briefs = load_briefs(tmp_path)
    assert match_brief(briefs, _read(("Some Off-Meta Deck", 0.3))) is None   # no covering Brief
    assert match_brief(briefs, _read()) is None                              # no candidates
    assert match_brief(briefs, None) is None                                 # no Read


# ---- resolve_brief_cards: name-keyed threats/targets -> card ids (the Board consumer's substrate) ----

def _ml_brief(**extra):
    """A Mega Lucario ex Brief carrying threats + role-tagged targets (name-keyed)."""
    return Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                 threats=extra.get("threats", [{"card": "Mega Lucario ex", "why": "270"}]),
                 targets=extra.get("targets", [{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"}]))


def test_resolve_brief_cards_maps_names_to_ids_and_roles():
    # A threat name -> a threat id; a target name -> {id: role}. Names resolve via the injected lookup.
    name_ids = {"Mega Lucario ex": {678}, "Riolu": {677}}
    threat_ids, target_roles = resolve_brief_cards(_ml_brief(), lambda n: name_ids.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {677: "fragile_preevo"}


def test_resolve_brief_cards_skips_unresolvable_names():
    # A name the lookup doesn't know resolves to no id -> silently skipped, never raises.
    threat_ids, target_roles = resolve_brief_cards(
        _ml_brief(targets=[{"card": "Ghost Card", "role": "engine", "why": "?"}]),
        lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {}                    # "Ghost Card" unknown -> dropped


def test_resolve_brief_cards_maps_a_name_to_all_its_ids():
    # A name printed under several card ids (reprints) maps ALL of them to the role.
    _, target_roles = resolve_brief_cards(
        _ml_brief(threats=[], targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "x"}]),
        lambda n: {"Riolu": {677, 6771}}.get(n, ()))
    assert target_roles == {677: "fragile_preevo", 6771: "fragile_preevo"}


def test_resolve_brief_cards_lists_a_card_that_is_both_threat_and_target():
    # Mega Lucario ex is BOTH a threat (respect) and a prize_liability target (exploit) -> both outputs.
    brief = _ml_brief(threats=[{"card": "Mega Lucario ex", "why": "270"}],
                      targets=[{"card": "Mega Lucario ex", "role": "prize_liability", "why": "3 prizes"}])
    threat_ids, target_roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "prize_liability"}


# ---- shipped-dir invariants (ADR-0038 hardening): the REAL briefs/ dir stays collision-free ----

def test_shipped_briefs_have_no_covers_collision():
    """REQ-BRIEF-0001: no archetype string appears in two shipped Briefs' `covers` — match_brief
    returns the alphabetically-first covering Brief, so an overlap would misroute SILENTLY."""
    seen: dict[str, str] = {}
    for brief in load_briefs():                    # the real src/common/scouting/briefs/ dir
        for arch in brief.covers:
            assert arch not in seen, (
                f"archetype {arch!r} covered by both {seen[arch]!r} and {brief.slug!r} — "
                f"every archetype string must route to exactly ONE Brief")
            seen[arch] = brief.slug
