# Strategy Ingestion

Glossary for the `strategy-ingest` skill: pull an external human-authored strategy source
(paid note.com articles now; video transcripts next), distil it into a committed, scope-tagged
**Strategy Digest** that a downstream grill (general-strategy authoring, `deck-genie`,
`matchup-genie`) turns into weighted **Hypotheses**. Only project-specific terms are defined here;
runtime terms (**Hypothesis**, **Read**, **Matchup Brief**, **Archetype**, **Function Tag**) are
canonical in their own contexts and reused verbatim.

## Language

**Source Adapter**:
The source-specific FETCH path that turns one external URL/file into a **Fetched Article**. Owns
everything source-specific: how to extract the body, how to check access/completeness, how to read
provenance. v1 ships the note.com adapter; the YouTube-transcript adapter is the second shape the
contract is validated against. Adding a source = a new adapter, never a change to Synthesis.
_Avoid_: scraper, parser, downloader.

**Fetched Article**:
The source-AGNOSTIC normalized intermediate a Source Adapter emits and the Synthesis stage consumes:
provenance (source, author/handle, url, title, date, language), an **access flag** (complete vs
paywalled/truncated/no-transcript), and a cleaned body — article text or a transcript. Its raw form
is saved locally under a gitignored path for re-parse; it never enters git.
_Avoid_: raw, page, download.

**Strategy Digest**:
The committed deliverable — one `<handle>_<slug>_strategy.md` per source. An English distillation
(not a translation) of one Fetched Article, sorted into the three **Actionability Buckets**, carrying
a provenance header (including the stable source id) and a `vintage` (an old-format source flags its era
and routes format-specific content to `Out-of-Scope (stale)`). A **series** source (a playlist / multi-part
course) is still ONE Digest, with per-episode provenance (`[E<n>]` tags). The unit a downstream grill
consumes.
_Avoid_: article, summary, translation, strategy.md (ambiguous).

**Actionability Bucket**:
The three sections every Digest sorts its points into: **Agent-Doctrine** (convertible to a Pilot
Hypothesis or Matchup Brief — the grill's actual input), **Process** (informs OUR
training/gauntlet/self-play workflow, not the Pilot), and **Out-of-Scope** (pure human-improvement
advice, captured briefly and flagged non-actionable).
_Avoid_: category, tag (reserve "Function Tag" for the card signal).

**Candidate Signal**:
The non-binding hint attached to each Agent-Doctrine entry, gesturing at what a future Hypothesis
*might* key on — a **Function Tag**, a board condition, a **Context** field, or the literal
"needs a new signal." It is scaffolding for the grill, never a committed trigger, id, or weight:
weights are ladder-tuned seeds and are never invented from an article.
_Avoid_: trigger, weight, hypothesis (a Candidate Signal is none of these yet).

**Scope / Target Home**:
Each Agent-Doctrine entry is tagged `general` | `our-deck:<deck>` | `opponent:<archetype>` and, where
it clearly targets an existing artifact, names it (`docs/general-strategy.md`,
`src/agents/<deck>/STRATEGY.md`, `docs/matchups/<slug>.md`). Best-effort against the tracked
**Archetype** vocabulary; an unmatched foreign deck name stays a described-opponent note.
_Avoid_: routing (informal), destination.
