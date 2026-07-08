---
name: strategy-ingest
description: >
  Download and distil an external human-authored Pokémon TCG strategy source (paid note.com articles
  now; video transcripts next) into a committed, scope-tagged Strategy Digest under
  data/strategy/<handle>_<slug>_strategy.md that a downstream grill (general-strategy authoring,
  /deck-genie, /matchup-genie) turns into weighted Hypotheses. Use whenever the user wants to pull in,
  ingest, download, parse, or digest an outside strategy article/video: "ingest this note.com article",
  "download and parse <url>", "/strategy-ingest <url>", "digest this strategy piece". It fetches through
  your already-logged-in browser (no credential handling) and STOPS on a paywall rather than mining a
  preview. Do NOT use it to author our own deck's doctrine (that's /deck-genie), opponent counterplay
  (/matchup-genie), or to tune weights from replays (/blunder-buster) — it only produces the Digest that
  feeds those grills.
---

# strategy-ingest — external strategy → a scope-tagged Digest

Turn ONE external human-authored strategy source (a paid note.com article now; a video transcript next)
into a committed, grill-ready **Strategy Digest**: `data/strategy/<handle>_<slug>_strategy.md`. The
Digest is an English distillation sorted by *where each point can go* — it is the **input** to a later
grill, not a weight change itself.

**Invocation:** `/strategy-ingest <url>` (one or more URLs). A **playlist/series URL** (e.g. a YouTube
`…/playlist?list=…`) is ONE source → **one series Digest**: enumerate the episodes, fetch each
transcript, synthesize once, with per-episode provenance on each claim (see *Series mode* below). Any
extra prose is ingest context — the source's topic, which of our decks it bears on — fold it into
Synthesis. Vocabulary
([CONTEXT.md](CONTEXT.md)): **Source Adapter**, **Fetched Article**, **Strategy Digest**, **Actionability
Bucket**, **Candidate Signal**, **Scope / Target Home**.

## The two stages (the seam)

Ingestion is two stages across one clean seam, so a new source is a new *fetch*, never a change to
*synthesis*:

1. **Source Adapter (fetch)** — source-specific. Turns one URL/file into a **Fetched Article**: the
   source-agnostic normalized intermediate (provenance + access-flag + cleaned body/transcript). The
   per-source recipe lives in `references/` — [note_com.md](references/note_com.md) (article sites, the
   one built) and [youtube.md](references/youtube.md) (video transcripts, the second shape the contract
   is validated against). The contract every adapter satisfies: [adapter_contract.md](references/adapter_contract.md).
2. **Synthesis (source-agnostic)** — reads a Fetched Article, writes the Digest. Never touches
   source-specific concerns. Rules + schema: [synthesis.md](references/synthesis.md); template:
   [assets/STRATEGY_DIGEST.template.md](assets/STRATEGY_DIGEST.template.md).

## Workflow

### Phase 0 · Orient (deterministic — silent, then Phase 1)

1. Pick the adapter from the input:
   - a **local `.txt` path** (e.g. under `data/strategy/transcripts/`) → the manual-transcript adapter,
     [manual_transcript.md](references/manual_transcript.md) (the working video path — parses a pasted
     transcript via `scripts/parse_transcript.py`);
   - a `note.com` host → [note_com.md](references/note_com.md);
   - a `youtube.com`/`youtu.be` **URL** → [youtube.md](references/youtube.md) — but automated transcript
     fetch is currently blocked YouTube-side (⛔), so route the user to the manual-transcript path instead;
   - unknown host → tell the user this source has no adapter yet and what a new one needs (per
     [adapter_contract.md](references/adapter_contract.md)); do not improvise a scraper.
2. **Idempotency:** derive the slug (below) and check `data/strategy/<handle>_<slug>_strategy.md`. If it
   exists and the user didn't say `--force`, stop and report it's already ingested.
3. Read [adapter_contract.md](references/adapter_contract.md) and [synthesis.md](references/synthesis.md)
   before fetching.

### Phase 1 · Fetch → Fetched Article (per the chosen adapter)

Run the adapter's recipe. It drives your **already-authenticated browser** (claude-in-chrome) — the
proof you've paid is that the full body renders. **Access guard (load-bearing):** before anything else,
check the adapter's completeness signal (note.com paywall/`続きを見る` block or a suspiciously short body;
YouTube: no transcript). If the article is locked or truncated → **STOP** and tell the user to
purchase/log in. **Never synthesize from a preview.**

Save the raw Fetched Article body under `data/strategy/raw/<handle>_<slug>.<ext>` (gitignored) so it can
be re-parsed without re-fetching. Emit the normalized Fetched Article struct in-session (provenance +
access-flag + cleaned body) for Synthesis.

**Series mode (playlist/multi-part course).** Enumerate the playlist's episodes (title + id + order),
then fetch each episode's body per the adapter. Concatenate into ONE Fetched Article whose `body` is the
episodes in order, each prefixed with an `## [E<n>] <title>` marker so Synthesis can attribute a claim to
its episode. The access guard is per-episode: a locked/transcript-less episode is skipped with a noted
gap, not a hard stop, as long as some episodes are `complete`. Raw goes to
`data/strategy/raw/<handle>_<series-slug>/E<n>_<slug>.<ext>`.

### Phase 2 · Synthesis → Strategy Digest (source-agnostic)

Per [synthesis.md](references/synthesis.md), distil the Fetched Article into
`data/strategy/<handle>_<slug>_strategy.md` from
[assets/STRATEGY_DIGEST.template.md](assets/STRATEGY_DIGEST.template.md):

- **English synthesis, not translation.** Keep the original Japanese title, author handle, and
  load-bearing JP deck/card names. Do **not** reproduce the article — this is your distillation.
- Sort every point into the three **Actionability Buckets**: **Agent-Doctrine**, **Process**,
  **Out-of-Scope**.
- Each **Agent-Doctrine** entry carries: **Scope** (`general` | `our-deck:<deck>` | `opponent:<archetype>`)
  + named **Target Home** (best-effort against the tracked Archetype vocab in
  [CONTEXT.md](../../../CONTEXT.md)) + the claim + why it wins games + a **Candidate Signal** hint. **No
  ids, no weights** — weights are ladder-tuned seeds, never invented from an article.
- Provenance header carries source, handle, title, url, the **stable source id**, date, language, and the
  access-flag.

### Phase 3 · Emit Strategy Proposals (terminal output — ADR-0046)

strategy-ingest is a producer: it **ends at fodder.** After writing the Digest, emit one **Strategy
Proposal** record per Agent-Doctrine entry into the unified queue `data/strategy/proposals/` (contract:
[../update-strategy/references/strategy_proposal_contract.md](../update-strategy/references/strategy_proposal_contract.md);
template: `../update-strategy/assets/STRATEGY_PROPOSAL.template.md`). Map each entry:
- `general` → `target_layer: general-hypothesis` (or `planner-code`), `verification_contract: seed-ladder`.
- `opponent:<archetype>` → `target_layer: matchup-brief`, `verification_contract: brief-validator`.
- `our-deck:<deck>` → `target_layer: deck-strategy`, `verification_contract: score-diff`.
Each record's `provenance` **links** to the Digest entry (never duplicates it); `candidate_signal` and the
claim become the thin `spec`. Then print a one-line summary of what was queued.

**Do NOT author or apply anything** — no Hypotheses, no Briefs, no code. `/update-strategy` drains the
queue and authors each proposal into its layer behind the right gate; the human commits there. One Digest
can fan out to several proposals across layers — that's expected.

## Slug & filename

`data/strategy/<handle>_<slug>_strategy.md`. **`<handle>`** = the author/channel handle from the source
(note.com URL `note.com/<handle>/n/<id>` → `<handle>`; YouTube → channel handle). **`<slug>`** = a short
lowercase-kebab English slug you derive from the title (≤5 words, meaningful). The **stable source id**
(note `n…` id / YouTube video id) and full URL live in the Digest's provenance header — that, not the
slug, is the dedupe key.

## What it is NOT

- **Not a weight change.** It writes a Digest; the downstream grill authors Hypotheses. Candidate Signals
  are hints, never committed triggers/ids/weights.
- **Not a translation.** English synthesis only — a full translation would republish paid content.
- **Not a credential store.** It rides your browser session; no cookies/tokens are handled or committed.
- **Not card-fact authority.** If a Digest asserts a card interaction, it's the *author's* claim — the
  engine + `data/EN_Card_Data.csv` remain ground truth; the downstream grill verifies before it ships.

## Copyright guard (load-bearing)

The raw Fetched Article is **paid, copyrighted** content: it is saved only under the gitignored
`data/strategy/raw/` and **never committed**. The committed Digest is your transformative English
synthesis — no full translation, no verbatim reproduction of the source body.

## Completion discipline — build the Digest to complete

Once invoked (and past the access guard), run to a finished Digest + routing summary in one push. Do not
end a turn reporting "fetched; synthesis remaining." Legitimate stops, exhaustively: (a) the access guard
tripped (paywall / no transcript / not logged in), (b) an unknown host with no adapter, (c) a genuinely
new scope decision the user must make. Everything else: keep going.
