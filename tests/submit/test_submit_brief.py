"""The Agent Brief's Manifest is an agent's decision-steering fingerprint (ADR-0019)."""
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

import re

from submit.brief import build_manifest, render_brief

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agents" / "mega_starmie"


def _agent_with_tuned(tmp_path, tuned: dict) -> Path:
    """A minimal agent dir (real strategy.py + deck.csv) with a chosen tuned.json overlay."""
    agent = tmp_path / "mega_starmie"
    agent.mkdir()
    shutil.copy(FIXTURE / "strategy.py", agent / "strategy.py")
    shutil.copy(FIXTURE / "deck.csv", agent / "deck.csv")
    (agent / "tuned.json").write_text(json.dumps(tuned), encoding="utf-8")
    return agent


@pytest.mark.req("REQ-SUB-0001")
def test_manifest_reports_effective_weight_overlaying_tuned_on_authored(tmp_path):
    agent = _agent_with_tuned(tmp_path, {"open-the-accelerator": 99.0})
    manifest = build_manifest(agent)

    hyp = next(h for h in manifest["general_strategy"]["hypotheses"]
               if h["id"] == "open-the-accelerator")
    assert hyp["authored"] == 40.0       # the authored seed (baseline_opening)
    assert hyp["effective"] == 99.0      # tuned.json overrides it
    assert hyp["overridden"] is True


@pytest.mark.req("REQ-SUB-0001")
def test_manifest_includes_general_strategy_hypotheses_with_overlay(tmp_path):
    agent = _agent_with_tuned(tmp_path, {"keep-a-bench": 77.0})
    manifest = build_manifest(agent)

    gen = manifest["general_strategy"]["hypotheses"]
    hyp = next(h for h in gen if h["id"] == "keep-a-bench")  # a shared General Strategy rule
    assert hyp["effective"] == 77.0      # the tuned overlay applies to general hyps too


@pytest.mark.req("REQ-SUB-0002")
def test_manifest_reports_tier_from_declared_search_budget(tmp_path):
    agent = tmp_path / "a"
    agent.mkdir()
    (agent / "strategy.py").write_text(
        "from common.strategy import Strategy\n"
        "STRATEGY = Strategy(name='a', params={'search_budget': 2})\n", encoding="utf-8")
    manifest = build_manifest(agent)

    assert manifest["capabilities"]["search_budget"] == 2
    assert manifest["capabilities"]["tier"] == 1     # search_budget > 0 => Tier-1 Search


@pytest.mark.req("REQ-SUB-0002")
def test_manifest_capability_flags_reflect_shipped_files(tmp_path):
    # a staged bundle: strategy + tuned overrides + a shipped card_functions.json, but no Posture artifact
    bundle = tmp_path / "b"
    (bundle / "common").mkdir(parents=True)
    (bundle / "strategy.py").write_text(
        "from common.strategy import Strategy\nSTRATEGY = Strategy(name='b')\n", encoding="utf-8")
    (bundle / "common" / "card_functions.json").write_text("{}", encoding="utf-8")
    (bundle / "tuned.json").write_text(json.dumps({"x": 1.0, "y": 2.0}), encoding="utf-8")

    caps = build_manifest(bundle)["capabilities"]
    assert caps["card_functions"]["present"] is True
    assert caps["posture"]["enabled"] is False       # no common/scouting/artifact.json shipped
    assert caps["overrides"]["count"] == 2           # two tuned weights ride along


@pytest.mark.req("REQ-SUB-0003")
def test_manifest_carries_provenance_join_keys_and_deck(tmp_path):
    agent = _agent_with_tuned(tmp_path, {})          # real strategy + the 60-card fixture deck
    manifest = build_manifest(agent, when=datetime(2026, 6, 25, 14, 30, 5), git_hash="abc1234")

    prov = manifest["provenance"]
    assert prov["agent"] == "mega_starmie"
    assert prov["git_hash"] == "abc1234"
    assert prov["built_at"].startswith("2026-06-25")
    deck = manifest["deck"]
    assert deck["size"] == 60
    counts = {c["id"]: c["count"] for c in deck["cards"]}
    assert sum(counts.values()) == 60                # duplicates collapsed into counts
    assert 1031 in counts                            # Mega Starmie ex is in the list


@pytest.mark.req("REQ-SUB-0003")
def test_manifest_deck_resolves_card_names_and_categories(tmp_path):
    agent = _agent_with_tuned(tmp_path, {})
    cards = {1031: {"name": "Mega Starmie ex", "category": "pokemon"}}
    deck = build_manifest(agent, cards=cards)["deck"]

    star = next(c for c in deck["cards"] if c["id"] == 1031)
    assert star["name"] == "Mega Starmie ex" and star["category"] == "pokemon"


@pytest.mark.req("REQ-SUB-0004")
def test_brief_renders_the_decklist_with_card_names_grouped(tmp_path):
    agent = _agent_with_tuned(tmp_path, {})         # real fixture deck + the committed card cache
    html = render_brief(build_manifest(agent, when=datetime(2026, 6, 25), git_hash="abc1234"))

    assert "Mega Starmie ex" in html                # real card names, not just "60 cards"
    # grouped into the standard decklist sections (the accented heading is rendered, not a JSON value)
    assert "Pokémon" in html and "Trainer" in html and "Energy" in html
    assert "3× Mega Starmie ex" in html             # count × name, like a real list


@pytest.mark.req("REQ-SUB-0004")
def test_brief_falls_back_to_size_when_no_card_db(tmp_path):
    agent = _agent_with_tuned(tmp_path, {})
    html = render_brief(build_manifest(agent, cards={}, when=datetime(2026, 6, 25), git_hash="abc1234"))

    assert "Deck — 60 cards" in html                # still shows the size header
    assert "<li" not in html                         # but no broken/empty decklist


@pytest.mark.req("REQ-SUB-0010")
def test_deck_diff_classifies_added_removed_and_recounted():
    from submit.brief import _deck_diff

    prev = {"cards": [{"id": 1, "count": 4, "name": "A"}, {"id": 2, "count": 2, "name": "B"},
                      {"id": 3, "count": 1, "name": "Gone"}]}
    cur = {"cards": [{"id": 1, "count": 4, "name": "A"}, {"id": 2, "count": 3, "name": "B"},
                     {"id": 4, "count": 2, "name": "New"}]}

    added, removed, changed, badges = _deck_diff(prev, cur)
    assert [c["id"] for c in added] == [4] and badges[4] == "new"
    assert [c["id"] for c in removed] == [3]                  # a card that left the deck
    assert changed[0]["id"] == 2 and (changed[0]["from"], changed[0]["to"]) == (2, 3)
    assert badges[2] == "+1"                                  # the inline recount marker


@pytest.mark.req("REQ-SUB-0010")
def test_deck_diff_is_empty_with_no_baseline_or_no_change():
    from submit.brief import _deck_diff, _deck_diff_html

    cur = {"cards": [{"id": 1, "count": 4, "name": "A"}]}
    assert _deck_diff(None, cur) == ([], [], [], {})         # first build: nothing to diff
    assert _deck_diff(cur, cur) == ([], [], [], {})          # rebuilt, same deck
    assert _deck_diff_html(2, [], [], []) == ""              # -> no callout rendered


@pytest.mark.req("REQ-SUB-0010")
def test_brief_renders_a_highlighted_deck_change_callout(tmp_path):
    agent = _agent_with_tuned(tmp_path, {})
    manifest = build_manifest(agent, when=datetime(2026, 6, 25), git_hash="abc1234")
    star = next(c for c in manifest["deck"]["cards"] if c.get("name") == "Mega Starmie ex")
    # a baseline that differs: one extra Mega Starmie ex, plus a now-removed tech card
    prev = {"cards": [{**c, "count": c["count"] + 1} if c is star else c
                      for c in manifest["deck"]["cards"]]
            + [{"id": 999999, "count": 2, "name": "Old Tech", "category": "item"}]}

    html = render_brief(manifest, prev_deck=prev, prev_build_id=4)
    assert "Deck changed since build #4" in html             # the highlighted callout
    assert "Old Tech" in html and "(removed)" in html        # the card that left
    assert "4 → 3" in html                                    # Mega Starmie ex recount (prev->cur)
    assert "deckdiff" in html and "class='changed'" in html  # styled callout + inline highlight


@pytest.mark.req("REQ-SUB-0008")
def test_manifest_surfaces_training_provenance_from_sidecar(tmp_path):
    agent = _agent_with_tuned(tmp_path, {"open-the-accelerator": 99.0})
    (agent / "tuned.meta.json").write_text(json.dumps(
        {"tuned_at": "2026-06-25T14:30:05", "corrections_count": 7, "corrections_hash": "abc123def456"}),
        encoding="utf-8")

    training = build_manifest(agent)["training"]
    assert training["corrections_count"] == 7
    assert training["corrections_hash"] == "abc123def456"


@pytest.mark.req("REQ-SUB-0004")
def test_brief_is_self_contained_and_embeds_recoverable_manifest(tmp_path):
    agent = _agent_with_tuned(tmp_path, {"open-the-accelerator": 99.0})
    manifest = build_manifest(agent, when=datetime(2026, 6, 25, 14, 30, 5), git_hash="abc1234")
    html = render_brief(manifest)

    # opens offline years from now: no external/CDN dependencies
    assert "http://" not in html and "https://" not in html
    # the machine-readable Manifest round-trips back out of the page
    m = re.search(r'<script type="application/json" id="manifest">(.*?)</script>', html, re.S)
    assert m, "the brief must embed the manifest JSON"
    assert json.loads(m.group(1)) == manifest


@pytest.mark.req("REQ-SUB-0004")
def test_brief_renders_expandable_hypothesis_rows_with_all_info(tmp_path):
    agent = _agent_with_tuned(tmp_path, {"open-the-accelerator": 99.0})
    html = render_brief(build_manifest(agent, when=datetime(2026, 6, 25, 14, 30, 5), git_hash="abc1234"))

    assert "<details" in html                     # expandable rows
    assert "open-the-accelerator" in html         # the hypothesis id (general, tuned per-deck)
    assert "99" in html                            # its effective (tuned) weight
    assert "Explosiveness" in html                # its rationale text (the human "all info")
    assert "lambda" in html                        # the trigger source is shown too



@pytest.mark.req("REQ-SUB-0005")
def test_package_ships_brief_and_drops_deck_txt_and_version_control(tmp_path):
    import zipfile

    from submit.package import package

    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE.parent)) as zf:
        names = zf.namelist()
        html = zf.read("brief.html").decode("utf-8")

    assert "brief.html" in names
    assert "deck.txt" not in names and "version_control.md" not in names  # ADR-0019: brief replaces them
    manifest = json.loads(re.search(r'id="manifest">(.*?)</script>', html, re.S).group(1))
    assert manifest["provenance"]["agent"] == "mega_starmie"
    assert manifest["capabilities"]["card_functions"]["present"] is True   # reads the real staged bundle
