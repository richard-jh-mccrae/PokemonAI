---
source: <note_com | youtube>
handle: <author/channel handle>
title: <original title / playlist title, verbatim — JP stays JP>
author_display: <human name if different from handle, else omit>
url: <canonical url>
source_id: <stable id — note n… id / youtube video id / playlist list_id>
kind: <single | series>
date: <YYYY-MM or YYYY-MM-DD — for a series, the earliest episode>
vintage: <current | sword-shield-era | other — set by synthesis Step 0>
language: <ja | en | …>
access: complete
ingested: <YYYY-MM-DD>
covers: <one line — what this source is about>
# series only — the episode manifest (omit for single):
episodes:
  - n: 1
    title: <episode title>
    id: <video id>
    access: <complete | no_transcript>
---

# Strategy Digest — <english short title>

<!-- Staleness banner — include ONLY when vintage != current: -->
> ⚠️ **Vintage: <era>.** Predates the Scarlet & Violet Mega-era format. General principles below
> transfer; deck/card/matchup specifics are a dead format and live under **Out-of-Scope (stale)** — do
> not treat them as current meta.

> English distillation of an external, paid/human-authored source. **Not** a translation and **not** a
> weight change — it is grill-fodder. Card interactions here are the *author's* claims; the engine +
> `data/EN_Card_Data.csv` remain ground truth (the downstream grill verifies before shipping). Series
> Digests tag each claim with its episode, e.g. `[E3]`.

## Agent-Doctrine

Convertible to a Pilot Hypothesis or a Matchup Brief — the grill's input. Each entry:
**scope** · **target home** · claim (why it wins) · *candidate signal* (a hint, not a weight/id/trigger).

### general
- **[general → docs/general-strategy.md]** <claim in 1–2 sentences; why it wins>.
  *Candidate signal:* <Function Tag / CardStat / board-or-Context condition / "needs a new signal">.

### opponent
- **[opponent:<archetype> → docs/matchups/<slug>.md]** <how this deck wins / how to beat it>.
  *Candidate signal:* <…>. <If no tracked-Archetype match: "described-opponent note — key Pokémon: <…>; no tracked Archetype match.">

### our-deck
- **[our-deck:<deck> → src/agents/<deck>/STRATEGY.md]** <claim; why it wins>.
  *Candidate signal:* <…>.

## Process

Informs OUR training/gauntlet/self-play workflow — not the Pilot. One line each.
- <process point — and the workflow it maps to, e.g. "≈ self-play corpus / blunder loop">.

## Out-of-Scope

Human-improvement advice with no repo home, plus format-bound specifics from an old-format source.
Captured to prove the source was fully mined. Non-actionable.
- <human-advice point> · *non-actionable*.
- <format-specific point, e.g. an old decklist/matchup call> · *(stale)* · <era>.

---

<!--
Delete unused scope sub-sections. If a bucket is empty, keep the heading with "(none)" so the Digest
shows the source was fully triaged, not skimmed.
-->
