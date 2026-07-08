# Source Adapter — YouTube (video transcripts)

Fetches one YouTube video's spoken strategy into a **Fetched Article** (contract:
[adapter_contract.md](adapter_contract.md)). This is the second adapter *shape* — it exists to keep the
seam honest: a different fetch and a different completeness check, feeding the **same** Synthesis. Build
it when the first video source is actually ingested; the recipe here is the contract it must satisfy.

## Identify

URL host is `youtube.com` (watch URL `…/watch?v=<source_id>`) or `youtu.be/<source_id>`. `<source_id>` is
the 11-char video id. `<handle>` is the channel handle (e.g. `@somechannel` → `somechannel`). A
**`…/playlist?list=<list_id>`** URL (or a `/watch?v=…&list=…`) is a **series** → run *Series mode*.

## Series mode (playlist)

1. `navigate` to the playlist URL. YouTube gates first-load behind a consent wall and renders the list
   with JS — plain fetchers (WebFetch) hit a consent redirect loop and see nothing, which is why this
   adapter drives the real browser. Dismiss the consent banner if present, then read the rendered list.
2. Enumerate every episode: order `<n>`, `title`, video id. This ordered list is the series manifest.
3. For each episode, run the single-video recipe below to get its transcript; concatenate per SKILL.md
   *Series mode* (one Fetched Article, `## [E<n>] <title>` markers, per-episode raw files). Skip an
   episode with no transcript, noting the gap — don't fail the whole series.
4. `handle` = channel; `source_id` = the `list_id`; `title` = the playlist title; `date` = the *earliest*
   episode's upload date (drives the vintage check — old series → stale format-specifics per synthesis
   Step 0).

## Fetch (drive the browser)

Ride the user's browser (claude-in-chrome). Load the core tools in one `ToolSearch` call, then:

1. `navigate` to the watch URL, then **pause playback** (`key: k`) — autoplay keeps the renderer busy and
   stalls screenshots/reads.
2. Extract the transcript (**the hard part — see below**).
3. Read provenance: `title` (video title, kept in its original language), `handle`/`source_id` (URL),
   `date` (upload date → `YYYY-MM`; visible near the view count), `language` (caption language). The
   description "Key moments"/chapters are a cheap outline if the transcript fails.

### Transcript extraction — what actually works (test findings, 2026-07-08, Get Gud Academy)

Transcript text is **not** trivially reachable. Confirmed on real videos:

- ❌ **`get_page_text` / `read_page` (a11y tree) do NOT expose transcript segments** — the transcript
  panel renders in a custom element whose segment text isn't surfaced as a11y nodes. You get the
  heading, never the lines.
- ❌ **The `timedtext` caption API is PoT-gated** — fetching a `captionTracks[].baseUrl` (even with
  `&fmt=json3`) returns **empty** without a proof-of-origin token. Don't rely on it.
- ⚠️ **The transcript UI panel via `javascript_tool` DOM scrape is the intended path but is finicky.**
  The panel (`ytd-transcript-renderer`) must be *opened and visible*, and segments
  (`ytd-transcript-segment-renderer`, `.segment-timestamp` + `.segment-text`) **lazy-render** — a single
  click + short wait often shows `segCount: 0`. Needs: ensure the engagement panel is visible, poll for
  segments (retry with backoff), and beware double-clicking the toggle (it closes the panel). The
  connection can also drop mid-session (transient).

### The hardened extraction routine (use this via `javascript_tool`)

Run this in the watch-page context (top-level await; it pauses the video, opens the panel **idempotently**
— never double-toggles it shut — and **polls** for the lazy render):

```js
document.querySelector('video')?.pause();
const segs = () => document.querySelectorAll('ytd-transcript-segment-renderer');
if (segs().length === 0) {
  const btn = [...document.querySelectorAll('button')].find(b =>
    /show transcript/i.test(b.getAttribute('aria-label') || '') ||
    /show transcript/i.test(b.innerText || ''));
  if (btn) btn.click();               // click ONLY when no segments — avoids toggling closed
}
let n = 0;
for (let i = 0; i < 24; i++) {         // ~12s max, 500ms backoff
  n = segs().length; if (n > 0) break;
  await new Promise(r => setTimeout(r, 500));
}
const lines = [...segs()].map(s => {
  const t = s.querySelector('.segment-timestamp')?.innerText.trim() || '';
  const x = s.querySelector('.segment-text, yt-formatted-string.segment-text')?.innerText.trim() || '';
  return t && x ? `${t} ${x}` : x;
}).filter(Boolean);
({ count: lines.length, text: lines.join('\n') });
```

Per video: `navigate` to the watch URL → run the routine → if `count === 0` after the poll, mark the
episode `no_transcript` and move on (never block the series). The connection can drop mid-run (transient)
— retry the call. Timestamps double as episode-relative cite anchors for the Digest's `[E<n>]` claims.

### ⛔ Root blocker found (2026-07-08): the transcript CONTENT does not load under automation

Hardening the scrape (idempotent open, poll, pause, description-expand) surfaced a deeper block the scrape
can't fix — **there is nothing to scrape**:

- Clicking "Show transcript" *does* expand the panel (`engagement-panel-searchable-transcript` →
  `ENGAGEMENT_PANEL_VISIBILITY_EXPANDED`, a "Close transcript" button appears), **but the panel stays
  empty** — `innerText` is just the "Transcript" heading, zero segment elements ever render, even after a
  long poll.
- YouTube now also ships a newer `PAmodern_transcript_view` panel; it too stays empty.
- Combined with the **PoT-gated `timedtext` caption API** (empty JSON), the signal is consistent: in this
  automated-browser context YouTube **does not serve the transcript payload at all**. The renderer is also
  unstable under automation (CDP `Runtime.evaluate` / screenshot timeouts, extension disconnects).

**Conclusion:** automated YouTube transcript ingest is **not currently viable** through claude-in-chrome —
the block is YouTube-side (transcript fetch gated), not a selector/timing bug. The scrape routine above is
retained for if/when the payload becomes reachable again.

**Working fallback (the supported YouTube path for now):** the user opens the video's transcript in their
own normal browsing, copies it (or uses a transcript site), and saves it to
`data/strategy/raw/<handle>_<series-slug>/E<n>_<slug>.txt`. Synthesis then runs source-agnostically over
those files exactly as if the adapter had produced them — a Fetched Article with `body_kind = transcript`,
`access = complete`. This keeps the real deliverable (the Digest) unblocked while the auto-fetch is dead.

## Access guard (the completeness check)

The video's equivalent of a paywall is **no transcript**:

- Captions disabled / no transcript panel → set `access = no_transcript` and **STOP**: tell the user this
  video has no captions to ingest (a future adapter could fall back to audio, out of scope now).
- Auto-generated captions are acceptable but note their lower fidelity in the Digest provenance
  (`language` + a note) so the grill weighs claims accordingly.

Only a usable transcript → `access = complete`.

## Emit

Save the transcript to `data/strategy/raw/<handle>_<slug>.txt` (gitignored), set `raw_path`, emit the
Fetched Article struct with `source = youtube`, `body_kind = transcript`. Synthesis treats a transcript
as lower-density, more repetitive prose than an article — distil harder, and be wary of spoken asides
that aren't real doctrine.
