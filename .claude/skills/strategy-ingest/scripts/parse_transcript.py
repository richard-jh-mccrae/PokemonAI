#!/usr/bin/env python3
"""Normalize a pasted video transcript into clean, citeable segments.

The manual-transcript source path of the ``strategy-ingest`` skill: the user pastes a raw
transcript (e.g. YouTube "Show transcript" copy) into ``data/strategy/transcripts/<name>.txt``;
this script turns the interleaved ``timestamp\\ntext`` lines into one ``[m:ss] text`` line per
segment, collapsing the caption line-wrap. The result is the source-agnostic **Fetched Article**
body (``body_kind = transcript``) that Synthesis consumes.

Also reads an optional provenance header at the top of the file — lines like ``# url: ...`` /
``# title: ...`` / ``# date: ...`` / ``# handle: ...`` before the first timestamp — and returns it
so the skill can fill the Digest's provenance without a separate prompt (it asks only for missing
required fields).

Cross-platform (pathlib, explicit utf-8). Pure function ``parse_transcript`` for testing; thin CLI.

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

# A pure timestamp line: M:SS, MM:SS, or H:MM:SS (optionally H:MM:SS). Whole line only.
_TS = re.compile(r"^\s*((?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})\s*$")
# A header line before the body: "# key: value" or "key: value" (key is a bare word).
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
    """Parse a pasted transcript.

    Returns ``(header, segments)`` where ``header`` is the leading provenance dict (possibly empty)
    and ``segments`` is a list of ``(start_seconds, text)`` in order. If the transcript carries no
    timestamps at all, the whole body is returned as one segment at t=0.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # 1. Header: contiguous key:value lines at the very top, before any timestamp or prose.
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
        break  # first non-header, non-blank, non-timestamp line ends the header

    # 2. Body: group text under the most recent timestamp.
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
    """Reflow fine-grained caption segments into coarser blocks.

    Raw auto-caption timestamps land every ~2s, giving hundreds of fragments. Group consecutive
    segments into a block that spans at least ``min_seconds`` (anchored at the block's start time),
    so the cleaned body reads as paragraphs with sparse, still-accurate cite anchors. ``min_seconds
    <= 0`` disables merging (one block per original segment).
    """
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
    """One ``[m:ss] text`` line per (possibly merged) block — the cleaned transcript body."""
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
    # Merge: 0:00 and 0:04 fall in one <30s block; 1:03:02 starts a new block.
    merged = merge_segments(segs, 30)
    assert merged[0] == (0, "one of the most important skills is something called sequencing"), merged
    assert merged[1] == (3782, "and this is much later"), merged
    assert merge_segments(segs, 0) == segs  # disabled
    # No-timestamp fallback: whole body as one segment.
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
