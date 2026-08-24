# ADR-TEMP-586 — Schema compatibility is a lossless migration chain

Supported evidence advances through validated one-version Corpus Migrations into the current
canonical schema while retaining its source hash, version, and migration identities. Unknown future
versions and any conversion requiring invented evidence are rejected instead of spreading version
unions through every verifier and Training View.
