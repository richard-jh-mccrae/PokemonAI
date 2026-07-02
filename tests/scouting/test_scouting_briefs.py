"""Brief-consumer runtime: load Matchup Briefs + match one to the Read (ADR-0027).

Offline, synthetic briefs. The bridge (load + match) mirrors artifact.load_artifact +
matchup.matchup_favorability; the Board wiring is behavior-neutral (nothing scores off it yet).
"""
import json

import pytest

from common.scouting.briefs import Brief, load_briefs, match_brief
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
