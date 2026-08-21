# ADR-0170 — Action caution is a decomposed valuation feature

The current `act_threshold` changes whether a turn-continuing action is selected after valuation, so it expresses a
strategic preference while remaining absent from contribution decomposition. #582 replaces it with an Action Opportunity
Cost feature whose coefficient lives in the resolved Valuation Configuration.

The decider compares the fully adjusted swing with zero. A configuration can preserve current behavior by assigning the
feature the equivalent cost, while tuning and diagnostics can attribute the result normally. Floating-point tolerance is
not strategy and belongs to Compute Configuration; it cannot be used as a second preference threshold.
