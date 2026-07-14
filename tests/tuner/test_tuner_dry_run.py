"""`tune.py --dry-run` is a READ-ONLY check: it prints the fit/proposals but writes NOTHING.

Guards the footgun that `tune.py` has no other read-only mode — every plain run recompiles the
committed `tuned.json` (+ meta + tuner ledger + report), so a verification / completion-gate run
must pass `--dry-run` or it silently clobbers the committed weights. The corpus, pilot, and fit are
stubbed so the test needs no engine and touches no real files — it asserts purely on whether the
write functions were invoked.
"""
import types

import train.tune as t


def _stub_run(monkeypatch, argv):
    """Run `tune.main(argv)` with the corpus/pilot/fit stubbed; return the list of write-fn names
    that fired (empty == nothing written)."""
    calls = []
    for name in ("write_overrides", "write_meta", "write_proposals"):
        monkeypatch.setattr(t, name, lambda *a, _n=name, **k: calls.append(_n))
    corr = types.SimpleNamespace(source="own", agent="x", agent_build=None)
    result = types.SimpleNamespace(overrides={}, proposals=[], skipped=[], unsatisfied=[],
                                   n_constraints=0, fit_adopted=False, base_satisfied=0)
    monkeypatch.setattr(t, "load_corrections", lambda store: [corr])
    monkeypatch.setattr(t, "load_reviewed", lambda p: {})
    monkeypatch.setattr(t, "partition_reviewed", lambda a, r: (a, []))
    monkeypatch.setattr(t, "_build_pilot", lambda agent: (object(), {}))
    monkeypatch.setattr(t, "tune", lambda *a, **k: result)
    monkeypatch.setattr(t, "sparse_overrides", lambda o, s: {})
    monkeypatch.setattr(t, "render_run_report", lambda *a, **k: "report")
    t.main(argv)
    return calls


def test_dry_run_writes_nothing(monkeypatch):
    """REQ-TUNER-0007: `--dry-run` invokes none of the write functions."""
    assert _stub_run(monkeypatch, ["--agent", "x", "--dry-run"]) == []


def test_plain_run_writes_the_overrides(monkeypatch):
    """Control: without `--dry-run` the same path DOES write (so the guard above can regress-catch)."""
    fired = _stub_run(monkeypatch, ["--agent", "x", "--no-report"])
    assert set(fired) == {"write_overrides", "write_meta", "write_proposals"}
