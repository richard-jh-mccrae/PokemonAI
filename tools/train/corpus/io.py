from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile


def canonical_bytes(value) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as target:
            target.write(canonical_bytes(value) + b"\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_gzip_jsonl(path: Path, rows) -> str:
    payload = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as target:
            target.write(payload)
    return digest_file(path)


def read_gzip_jsonl(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)
