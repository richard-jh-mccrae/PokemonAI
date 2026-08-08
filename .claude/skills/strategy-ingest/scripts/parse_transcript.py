#!/usr/bin/env python3
"""Normalize a pasted video transcript (``timestamp\\ntext`` lines) into ``[m:ss] text`` segments plus
an optional leading provenance header — the ``strategy-ingest`` skill's ``body_kind = transcript``.

Usage:
    python parse_transcript.py <input.txt> [--out <cleaned.txt>] [--json]
    python parse_transcript.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TS = re.compile(r"^\s*((?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})\s*$")
_HEADER = re.compile(r"^\s*#?\s*(?P<key>[A-Za-z_]+)\s*:\s*(?P<val>.+?)\s*$")

_HEADER_KEYS = {"url", "title", "date", "handle", "author", "source", "language", "series"}


def _ts_seconds(m: re.Match) -> int:
    h = int(m.group("h") or 0)
    return h * 3600 + int(m.group("m")) * 60 + int(m.group("s"))


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_transcript(text: str) -> tuple[dict[str, str], list[tuple[int, str]]]:
    """Returns ``(header, segments)`` of ``(start_seconds, text)``; a transcript with NO timestamps
    yields the whole body as one segment at t=0."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    header: dict[str, str] = {}
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        if _TS.match(raw):
            break
        hm = _HEADER.match(raw)
        if hm and hm.group("key").lower() in _HEADER_KEYS:
            header[hm.group("key").lower()] = hm.group("val").strip()
            i += 1
            continue
        break

    segments: list[tuple[int, str]] = []
    cur_t: int | None = None
    cur_words: list[str] = []

    def flush() -> None:
        if cur_words:
            txt = re.sub(r"\s+", " ", " ".join(cur_words)).strip()
            if txt:
                segments.append((cur_t or 0, txt))

    for raw in lines[i:]:
        ts = _TS.match(raw)
        if ts:
            flush()
            cur_t = _ts_seconds(ts)
            cur_words = []
        else:
            stripped = raw.strip()
            if stripped:
                cur_words.append(stripped)
    flush()

    return header, segments


def merge_segments(
    segments: list[tuple[int, str]], min_seconds: int = 30
) -> list[tuple[int, str]]:
    """Raw auto-caption timestamps land every ~2s, so group consecutive segments into blocks spanning
    >= ``min_seconds``, anchored at the block's start time. ``min_seconds <= 0`` disables merging."""
    if min_seconds <= 0 or not segments:
        return segments
    blocks: list[tuple[int, str]] = []
    start_t, words = segments[0][0], [segments[0][1]]
    for t, txt in segments[1:]:
        if t - start_t >= min_seconds:
            blocks.append((start_t, " ".join(words)))
            start_t, words = t, [txt]
        else:
            words.append(txt)
    blocks.append((start_t, " ".join(words)))
    return blocks


def render(segments: list[tuple[int, str]]) -> str:
    return "\n".join(f"[{_fmt(t)}] {txt}" for t, txt in segments)


def _selftest() -> int:
    sample = (
        "# url: https://youtu.be/abc\n"
        "# title: Sequencing\n"
        "0:00\n"
        "one of the most important\n"
        "skills is\n"
        "0:04\n"
        "something called sequencing\n"
        "1:03:02\n"
        "and this is much later\n"
    )
    header, segs = parse_transcript(sample)
    assert header == {"url": "https://youtu.be/abc", "title": "Sequencing"}, header
    assert segs[0] == (0, "one of the most important skills is"), segs[0]
    assert segs[1] == (4, "something called sequencing"), segs[1]
    assert segs[2] == (3782, "and this is much later"), segs[2]
    assert render(segs).splitlines()[0] == "[0:00] one of the most important skills is"
    assert render(segs).splitlines()[2] == "[1:03:02] and this is much later"
    merged = merge_segments(segs, 30)
    assert merged[0] == (0, "one of the most important skills is something called sequencing"), merged
    assert merged[1] == (3782, "and this is much later"), merged
    assert merge_segments(segs, 0) == segs
    h2, s2 = parse_transcript("just some prose\nwith no timestamps")
    assert h2 == {} and s2 == [(0, "just some prose with no timestamps")], (h2, s2)
    print("parse_transcript selftest: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize a pasted video transcript.")
    ap.add_argument("input", nargs="?", help="path to the pasted transcript .txt")
    ap.add_argument("--out", help="write cleaned transcript here (default: stdout)")
    ap.add_argument("--json", action="store_true", help="emit {header, segments, cleaned} as JSON")
    ap.add_argument(
        "--merge-seconds", type=int, default=30,
        help="reflow caption fragments into blocks spanning >= N seconds (0 = raw per-segment)",
    )
    ap.add_argument("--selftest", action="store_true", help="run built-in assertions and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.input:
        ap.error("input is required (or use --selftest)")

    text = Path(args.input).read_text(encoding="utf-8")
    header, segments = parse_transcript(text)
    segments = merge_segments(segments, args.merge_seconds)
    cleaned = render(segments)

    if args.json:
        payload = {
            "header": header,
            "segments": [{"t": t, "text": x} for t, x in segments],
            "cleaned": cleaned,
        }
        out = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        out = cleaned

    if args.out:
        Path(args.out).write_text(cleaned + "\n", encoding="utf-8")
        print(
            f"parsed {len(segments)} segments"
            f"{f' + header {sorted(header)}' if header else ''} -> {args.out}",
            file=sys.stderr,
        )
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
