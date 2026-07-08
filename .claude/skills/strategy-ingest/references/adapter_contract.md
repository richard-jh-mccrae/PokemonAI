# The Source Adapter contract — the Fetched Article

Every **Source Adapter** (article site, video transcript, …) does exactly one job: turn one URL/file
into a **Fetched Article** — the source-AGNOSTIC normalized intermediate that Synthesis consumes. Get
this shape right and Synthesis never needs to know where the content came from; adding a source is a new
adapter file in `references/`, nothing else.

## The Fetched Article struct

An adapter emits (in-session, for Synthesis) this normalized object:

| field | meaning | notes |
|---|---|---|
| `source` | source kind | `note_com`, `youtube`, … (matches the adapter) |
| `source_id` | the STABLE per-source id | note `n…` id; YouTube video id. The dedupe key. |
| `url` | canonical URL | |
| `handle` | author/channel handle | drives the filename `<handle>` |
| `author_display` | human display name if different | optional |
| `title` | original title | kept verbatim (JP stays JP) |
| `date` | publish date | `YYYY-MM` or `YYYY-MM-DD`, best-effort |
| `language` | body language | e.g. `ja` |
| `access` | **the completeness flag** | `complete` \| `paywalled` \| `truncated` \| `no_transcript` |
| `body` | cleaned main content | article text OR transcript; source chrome stripped |
| `body_kind` | `article` \| `transcript` | lets Synthesis expect prose vs spoken text |
| `raw_path` | where the raw body was saved | `data/strategy/raw/<handle>_<slug>.<ext>` (gitignored) |

## The three responsibilities every adapter owns

1. **Extract the body** — pull the main content, strip site chrome (nav, comments, recommendations,
   ads). Article: the post body. Video: the transcript/captions (with timestamps if cheap).
2. **Report access** — set `access` honestly. This is the load-bearing guard: Synthesis refuses to run
   unless `access == complete`. An adapter must know its source's "you don't have this" signal (note.com
   paywall block; a video with captions disabled).
3. **Read provenance** — `source_id`, `handle`, `title`, `date`, `language` from the page/metadata, not
   from the user's prose.

## Rules for adapters

- **No credential handling.** Adapters ride the user's already-authenticated browser
  (claude-in-chrome). No cookies, tokens, or passwords are read, stored, or committed.
- **Raw is gitignored.** Always save the raw body under `data/strategy/raw/` and set `raw_path`; never
  write raw content anywhere committed.
- **Fail loud on access.** If the content is locked/truncated/missing, set `access` accordingly and let
  the workflow STOP. Never fabricate or complete missing content.
- **Source-specific stays in the adapter.** Selectors, paywall markers, transcript endpoints — all live
  in the adapter file. Synthesis reads only the struct above.

## Adding a new source later

Write a new `references/<source>.md` with: how to identify its URLs, how to drive the browser (or read
the local file) to extract the body, the exact `access` signal, and how to read provenance. Then add the
host → adapter mapping to SKILL.md Phase 0. Synthesis and the Digest schema are untouched — that's the
point of the seam. (PDFs and social/forum threads are foreseen but unbuilt; a PDF adapter would set
`access = complete` on "you have the file" and skip the browser entirely.)
