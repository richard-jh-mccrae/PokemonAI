# Submission

`package.py` stages a deck declaration, shared `common/`, and native `cg/`, then creates a zip.
`cgpy/` is offline-only diagnostics/testing/simulation and is categorically forbidden from Kaggle
artifacts. The artifact test scans every ZIP path and every file's bytes for that forbidden name.
The embedded HTML/CSV brief records provenance, deck contents, Bellman system identity, Roles,
evolution Lines, starter order, partners, prize plan, and capabilities.

`build.py` records the artifact in the local build ledger. `submit.py` checks and uploads that exact
artifact. The exact-bundle mirror is bounded to 600 seconds and the Kaggle upload to 120 seconds:
a timeout is a visible failed gate and is never recorded as a submission. `collect.py`, `history.py`, and
`dashboard.py` retain submission/performance history.

Legacy hypotheses, tuning overlays, and composer inventories are not packaged.
