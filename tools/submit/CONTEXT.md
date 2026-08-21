# Submission

`package.py` stages a deck declaration, shared `common/`, and native `cg/`, then creates a zip.
`cgpy/` is offline-only diagnostics/testing/simulation and is categorically forbidden from Kaggle
artifacts. The artifact test scans every ZIP path and every file's bytes for that forbidden name.
The embedded HTML/CSV brief records provenance, deck contents, the Ledger weight vector, Roles,
evolution Lines, starter order, partners, prize plan, and capabilities.

`build.py` records the artifact in the local build ledger. `submit.py` checks and uploads that exact
artifact. The exact-bundle mirror is bounded to 600 seconds and the Kaggle upload to 120 seconds:
a timeout is a visible failed gate and is never recorded as a submission. `collect.py`, `history.py`, and
`dashboard.py` retain submission/performance history.

On mirror timeout, the complete subprocess tree is terminated so Windows releases native `cg.dll`.
The CLI reports stage, reason, and whether upload ran. Set `SUBMIT_AGENT_DEBUG=1` only when a full
unexpected-exception traceback is needed.

Legacy hypotheses, tuning overlays, and composer inventories are not packaged.
