# ADR-0189 — The Canonical Corpus is manifested JSONL

The Canonical Corpus uses deterministic content-addressed gzip JSONL shards referenced by immutable
snapshot manifests. Unchanged canonical shards are reused; Arrow becomes a pinned dependency for
cached Parquet Training Views while evidence validity remains independent of that binary library.
