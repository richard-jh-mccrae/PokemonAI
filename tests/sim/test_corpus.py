"""Corpus v2 generator (tools/sim/corpus, ADR-0053 WP0): pure helpers, plus one live mirror run."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]


@pytest.mark.req("REQ-SIM-0016")
def test_corpus_pairings_matrix_covers_cross_mirror_and_opponents():
    from sim.corpus import corpus_pairings
    agents_only = corpus_pairings(["ms", "ml", "dp"])
    assert set(agents_only) == {("ms", "ms"), ("ms", "ml"), ("ms", "dp"),
                                ("ml", "ml"), ("ml", "dp"), ("dp", "dp")}
    with_opp = corpus_pairings(["ms", "ml"], opponents=("meta_x",))
    assert set(with_opp) == {("ms", "ms"), ("ms", "ml"), ("ml", "ml"),
                             ("ms", "meta_x"), ("ml", "meta_x")}
    assert ("meta_x", "meta_x") not in with_opp                       # we only learn OUR seats


@pytest.mark.req("REQ-SIM-0016")
def test_next_index_is_the_crash_safe_resume_cursor(tmp_path):
    from sim.corpus import film_name, next_index
    assert next_index(tmp_path) == 0
    assert film_name(0, 111).endswith(".json.gz")
    (tmp_path / film_name(0, 111)).write_text("{}", encoding="utf-8")
    (tmp_path / film_name(3, 222)).write_text("{}", encoding="utf-8")  # gap at 1,2 (crashed/skipped)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")    # not a film -> ignored
    assert next_index(tmp_path) == 4                                  # max index, not a file count


@pytest.mark.req("REQ-SIM-0016")
def test_per_pairing_target_spreads_the_game_cap():
    from sim.corpus import per_pairing_target
    assert per_pairing_target(30_000, 6) == 5000
    assert per_pairing_target(30_000, 6, explicit=100) == 100
    assert per_pairing_target(3, 6) == 1                              # floored at 1, never 0
    assert per_pairing_target(100, 0) == 0


@pytest.mark.req("REQ-SIM-0016")
def test_cap_hit_reports_the_binding_cap():
    from sim.corpus import cap_hit
    caps = {"max_games": 100, "max_bytes": 1000}
    assert cap_hit({"games": 50, "bytes": 500}, caps) is None
    assert cap_hit({"games": 100, "bytes": 500}, caps) == "max_games"
    assert cap_hit({"games": 50, "bytes": 1000}, caps) == "max_bytes"


@pytest.mark.req("REQ-SIM-0016")
def test_build_manifest_pins_the_shape_contract():
    from sim.corpus import BELLMAN_CORRECTION_FORMAT, MANIFEST_VERSION, build_manifest
    m = build_manifest(run_id="r1", created_at="2026-07-13T00:00:00", git_rev="abc1234",
                       agents=["ms", "ml"], opponents=(), agent_versions={"ms": "abc1234"},
                       per_pairing=50, max_games=30_000, max_bytes=1 << 33)
    assert m["manifest_version"] == MANIFEST_VERSION
    assert m["corpus_schema"]["bellman_correction_format"] == BELLMAN_CORRECTION_FORMAT
    assert m["corpus_schema"]["replay_shape"] == "cabt-visualize"
    assert m["status"] == "running" and m["totals"] == {"games": 0, "bytes": 0}
    assert {(p["a"], p["b"]) for p in m["pairings"]} == {("ms", "ms"), ("ms", "ml"), ("ml", "ml")}
    assert all(p["done"] == 0 and p["target"] == 50 for p in m["pairings"])


@pytest.mark.req("REQ-SIM-0016")
def test_prune_runs_reclaims_oldest_complete_only(tmp_path):
    from sim.corpus import prune_runs
    root = tmp_path / "corpus"

    def _run(rid, created, status):
        d = root / rid
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(
            json.dumps({"run_id": rid, "created_at": created, "status": status}), encoding="utf-8")
        (d / "film.json").write_text("x" * 1000, encoding="utf-8")

    _run("old", "2026-07-01", "complete")
    _run("mid", "2026-07-05", "complete")
    _run("live", "2026-07-09", "running")

    deleted = prune_runs(root, keep_bytes=0)                          # force reclaim of all complete
    assert deleted == ["old", "mid"]                                 # oldest-first, running excluded
    assert not (root / "old").exists() and not (root / "mid").exists()
    assert (root / "live").exists()


@pytest.mark.req("REQ-SIM-0017")
def test_generate_corpus_run_writes_manifest_and_resumes(tmp_path):
    """Disk, not the manifest, is the authoritative resume cursor."""
    from sim.corpus import generate_corpus_run
    from train.blunder.decisions import iter_decisions
    from meta_tracker.parse import load_replay

    kw = dict(run_id="t1", created_at="2026-07-13T00:00:00", git_rev="abc1234",
              agents=["mega_starmie"], agents_root=FIXTURE_AGENTS, out_root=tmp_path,
              agent_versions={"mega_starmie": "abc1234"}, per_pairing=2, extra_syspath=SRC)

    run_dir = generate_corpus_run(**kw)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["totals"]["games"] == 2
    films = sorted(run_dir.rglob("*.json.gz"))
    assert len(films) == 2 and all(f.parent.name == "mega_starmie__mega_starmie" for f in films)

    decisions = iter_decisions(load_replay(films[0]))
    assert len(decisions) > 10 and all(decision.obs is not None for decision in decisions)

    run_dir2 = generate_corpus_run(resume=True, **kw)                # same run_id -> resume
    films2 = list(run_dir2.rglob("*.json.gz"))
    assert len(films2) == 2                                          # target already met -> nothing new
    manifest2 = json.loads((run_dir2 / "manifest.json").read_text(encoding="utf-8"))
    assert manifest2["totals"]["games"] == 2                         # reconciled from disk, not doubled
    assert manifest2["status"] == "complete"
