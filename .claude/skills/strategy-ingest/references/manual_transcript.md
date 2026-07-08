# Source Adapter — manual transcript (local file, no browser)

The **paste-a-transcript** path — the working YouTube route while automated fetch is dead (see
[youtube.md](youtube.md) ⛔), and the general fallback for any spoken/video source. It's the
contract's *local-file, no-browser* branch: `access` is `complete` because **the file exists**.

## Identify

The skill is invoked on a **local `.txt` path** instead of a URL, e.g.
`/strategy-ingest data/strategy/transcripts/mellowmagikarp_sequencing.txt`. Anything under
`data/strategy/transcripts/` (gitignored — copyrighted spoken content) is a manual transcript.

## The user's part

1. Open the video, **Show transcript**, copy it (or use a transcript site).
2. Paste into `data/strategy/transcripts/<name>.txt` — raw is fine (the interleaved
   `timestamp\ntext` caption format is exactly what the parser expects).
3. **Optional provenance header** at the very top (before the first timestamp), one per line — the
   parser reads these so the skill doesn't have to ask:
   ```
   # url: https://www.youtube.com/watch?v=...
   # title: <video title>
   # date: 2024-05
   # handle: MellowMagikarp
   ```

## Fetch → Fetched Article (deterministic)

Run the parser — it strips the caption line-wrap and reflows into coarse, citeable blocks, and
returns any provenance header:

```
python .claude/skills/strategy-ingest/scripts/parse_transcript.py \
    data/strategy/transcripts/<name>.txt \
    --out data/strategy/transcripts/<name>.cleaned.txt --json
```

- `--merge-seconds N` (default 30) groups the ~2s caption fragments into `[m:ss]`-anchored blocks;
  `0` keeps them raw. The anchors are episode-relative cite points for the Digest.
- `--selftest` runs the built-in assertions.

Emit the Fetched Article: `source = youtube` (or the real platform), `body_kind = transcript`,
`access = complete`, `body` = the cleaned blocks. Provenance = the parsed header; **for any missing
required field (`url`, `title`, `date`), ask the user once** — a transcript has no metadata of its own.

## Then

Hand to [synthesis.md](synthesis.md) unchanged. The transcript's `date` still drives the vintage
check (Step 0): a current-era source whose *card examples* are real-TCG (not necessarily in the
competition's Mega-era sim pool) keeps the transferable **principles** as `general` doctrine and
treats the card names as the author's illustrations — verify against `data/EN_Card_Data.csv`, never
promote a real-TCG card example to an `opponent`/`our-deck` entry on faith.
