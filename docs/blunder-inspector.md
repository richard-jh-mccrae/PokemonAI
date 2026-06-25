# Blunder inspector (`tools/train/blunder/`)

Offline tool to step through a replay in the **official cabt viewer**, tag a Decision as a
blunder, and emit a **Correction** — curated training signal for Job A weight-tuning
([ADR-0009](adr/0009-training-methodology.md)). Trends across submissions surface what our
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
`vite:singlefile`, so it runs with no server-side assets. **Offline caveat:** the only
external reference is a Google Fonts stylesheet for toolbar *icon glyphs* — the board and
cards render fully offline; without internet the toolbar icons fall back to text.

## Run

```
python tools/train/blunder_correction.py <replay.json|.gz> --team <ours> --agent mega_starmie
python tools/train/blunder_report.py                         # rebuild the trend report
python -m pytest tests/test_blunder_*.py -q                  # data-spine tests (REQ-BLUNDER-####)
```
