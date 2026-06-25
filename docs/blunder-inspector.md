# Blunder inspector (`tools/train/blunder/`)

Offline tool to step through a replay in the **official cabt viewer**, tag a Decision as a
blunder, and emit a **Correction** — curated training signal consumed by the
[Blunder Tuner](blunder-tuner.md) (Job A, [ADR-0009](adr/0009-training-methodology.md)). Trends across submissions surface what our
agents get wrong over the competition. See the [Training context](../tools/train/CONTEXT.md),
[ADR-0014](adr/0014-blunder-inspector-viewer-engine.md) (viewer), and
[ADR-0015](adr/0015-correction-schema.md) (schema).

## Data spine (Python)

| Module | Responsibility |
|---|---|
| `decisions.py` | `iter_decisions(replay)` → `Decision`s from the full-info `visualize` film |
| `decode.py` | `option_label(option, current)` → readable dropdown labels |
| `categories.py` | the closed Category vocabulary + `is_valid_category` |
| `correction.py` | `Correction` + `build_correction(...)` with validation |
| `store.py` | append-only JSONL log at `data/corrections/corrections.jsonl` (committed) |
| `seats.py` | `detect_seat(replay, team_name)` — which seat is ours |
| `report.py` | `summarize(...)` + `build_report(log, out)` → offline HTML trends |

A **Decision** = one engine `select` at one frame; `chosen`/`correct` index `select.option`.
A **Correction** embeds a self-contained snapshot, so it outlives the replay (ADR-0015).

## Category vocabulary (extensible, by process)

`missed_win`, `missed_ko`, `bad_target`, `prize_mismanagement`, `misattachment`,
`wasted_resource`, `slow_setup`, `overextension`, `bad_retreat`, `ignored_threat`,
`sequencing_error`, `other`. Add a term in `categories.py` when a real blunder doesn't fit.

## Viewer (`tools/train/blunder/viewer/`)

The official Kaggle visualizer, vendored + built offline ([ADR-0014](adr/0014-blunder-inspector-viewer-engine.md)),
embedded in an iframe inside the tagging shell; the shell feeds it the replay via
`postMessage({replay})`. One-time build (needs Node + corepack):

```
python tools/train/blunder/viewer/build.py     # clones kaggle-environments, pnpm build -> dist/index.html
```

The build inlines everything into a single self-contained `dist/index.html` (~600 KB) via
`vite:singlefile`, so it runs with no server-side assets.

**Two viewers (see [ADR-0014](adr/0014-blunder-inspector-viewer-engine.md) amendment):**
- The vendored OSS board is **plain** (text + lines, no card art) but **offline** — the iframe default.
- The **colorful** dynamic viewer (as shown online) is a **HEROZ-hosted, online-only** web
  app (`ptcgvis.heroz.jp`); the shell's **🎨 colorful** button POSTs the replay to it
  (embedded in the iframe if HEROZ allows framing, else a new tab). HEROZ's page is
  cross-origin, so you tag in the side panel — which indexes frames by the **same step
  `X / N`** the viewer shows (read the step from the viewer, type it in the panel, land on
  the exact frame). The panel's "engine selected" mirrors the viewer's "Selected Action":
  the film records a select's choice in the **next** frame (offset +1), which the code
  accounts for, so `chosen` is a valid option position. You read the move in the colorful
  viewer and pick the **correct** move from the panel's option list.
- An **"Analyze as"** selector (P0 / P1 / both self-play) picks which seat is *us*: it flips
  the viewer's perspective and auto-labels each saved blunder **own** (your agent + submission)
  or **peer** (the opponent's team name) from the frame's acting seat — so both players'
  blunders are taggable in one pass.

## Run

```
python tools/train/blunder_correction.py <replay.json|.gz> --team <ours> --agent mega_starmie
python tools/train/blunder_report.py                         # rebuild the trend report
python -m pytest tests/test_blunder_*.py -q                  # data-spine tests (REQ-BLUNDER-####)
```
