# ADR-0164 — Only our deck overlays valuation

Ledger resolves one Valuation Configuration from general coefficients plus our deck's sparse residuals. Opponent candidates
describe uncertain facts through typed Roles and traits; they do not carry a second set of preferences. Mixing candidate
coefficients with candidate activations would make posterior movement change both the believed world and the valuation
ruler used to measure it.

Existing Brief `ledger_overrides` therefore do not survive as overlays. Still-valid intent must become a typed opponent
claim and compile into contextual Valuation Features; obsolete declarations retire under #555. The resolved configuration
remains complete, deterministic, and independently hashable from the #559 Opponent Snapshot.
