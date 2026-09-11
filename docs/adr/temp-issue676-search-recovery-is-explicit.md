# ADR-TEMP-676 — Search recovery is explicit

A non-permitting Search Outcome never enters normal Decision Policy. An explicitly configured Fail-safe
Policy may recover only the outcome classes and roster evidence declared compatible, while Decision Result
preserves the original failure and recovery reason; otherwise no action is returned. Ledger retains its
current typed fail-safe through a compatibility adapter, while PUCT retains stop-on-unusable behavior and
independent algorithms receive no fallback automatically.

Fail-safe Policy consumes its own typed request carrying the original outcome, failure, roster, and surviving
evidence under declared requirements. It returns Action Choice Identity plus recovery evidence; weakening the
normal Decision Policy Request with optional failed-search fields was rejected.

The coordinator has no implicit second recovery. Ledger preserves its deterministic neutral lottery through
an explicitly configured composite Fail-safe Policy that records primary failure before the secondary choice;
other algorithms receive no such behavior unless declared. Exhausting the configured recovery returns typed
No Selection, and #678 later includes the resolved recovery composition in Behavior Identity.
