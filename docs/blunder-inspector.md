# Blunder inspector (`tools/train/blunder/`)

Offline tool to step through a replay in the **official cabt viewer**, tag a Decision — or a whole
Turn or Match — as a blunder, and emit a **Correction**: curated training signal consumed by the
[Blunder Tuner](blunder-tuner.md) (Job A, [ADR-0009](adr/0009-training-methodology.md)). Trends across submissions surface what our
agents get wrong over the competition. See the [Training context](../tools/train/CONTEXT.md),
[ADR-0014](adr/0014-blunder-inspector-viewer-engine.md) (viewer),
[ADR-0015](adr/0015-correction-schema.md) (schema), and
[ADR-0049](adr/0049-corrections-carry-a-scope-decision-turn-or-match.md) (scope).

## Data spine (Python)

| Module | Responsibility |
|---|---|
| `decisions.py` | `iter_decisions(replay)` → `Decision`s from the full-info `visualize` film |
| `decode.py` | `option_label(option, current)` → readable dropdown labels |
| `categories.py` | the closed Category vocabulary + `is_valid_category` |
| `correction.py` | `Correction` + `build_correction(...)` with validation |
| `store.py` | per-build correction tree `data/corrections/<agent_build>/corrections.jsonl` (committed); routes by `agent_build`, reads union the tree, **dedup by default** |
| `seats.py` | `detect_seat(replay, team_name)` — which seat is ours |
| `report.py` | `summarize(...)` + `avg_blunders_per_game(...)` (own blunders ÷ distinct tagged games, by build over time) + `build_report(log, out, *, reviewed_path, proposals_dir)` → offline HTML trends; given the reviewed ledger + the `data/corrections/tuner` snapshot it also badges each blunder **fixed / covered / refuted / deferred / open / skipped** and splits resolved vs open |

A **Decision** = one engine `select` at one frame; `chosen`/`correct` index `select.option`.
A **Correction** embeds a self-contained snapshot, so it outlives the replay (ADR-0015).

## Scope — a tag can be about a Decision, a Turn, or a Match

Not every blunder is one bad pick. A turn can be lost by a *set* of individually defensible
Decisions played in the wrong order; a match can be lost to a wrong Game Plan that no single
`select` reveals. The panel's **Scope** selector says what the tag is about
([ADR-0049](adr/0049-corrections-carry-a-scope-decision-turn-or-match.md)):

| Scope | Subject (its identity) | `correct` | Span embedded | Verified by |
|---|---|---|---|---|
| `decision` (default) | the Anchor frame | mandatory | — | `retest` — the blunder is `fixed` or not |
| `turn` | the turn number + seat | **optional** | every Decision of that turn, with its `obs` | `retest_span` — re-drive to the **first divergence** |
| `match` | the seat | forbidden | per-turn headers for both seats, + `game_plan` | the ladder (`seed-ladder`) — nothing plans across turns |

You always tag from an **Anchor**: a real Decision frame, the point you were looking at. It is
context and provenance, *never identity* — the same turn tagged from two different frames is one
Correction.

A `turn`-scope `correct` is optional because a multi-frame counterfactual line **cannot** be
expressed as option indices: prescribing a different pick at the Anchor invalidates every later
frame's `select.option`, which only exists because the original pick was made. So at most one
prescription is sound — the first divergent Decision — and giving it *is* the claim that this
Anchor is that Decision. Leave it empty and the intended line lives in the `rationale`.

Turn 0 is the shared **setup phase** — both seats act in it — which is why a turn's identity
carries the seat and not just the number.

**One Correction per subject (enforced).** `record_correction` refuses a second tag on a subject
already corrected — `a correction already exists at this turn … edit or remove it first` — so
conflicting tags can't be created. A Turn Correction and the Decision Corrections *inside* that
turn are different subjects, so they coexist. To change a call, use the panel's **edit** (it passes
`replace_id` so refining its own tag is allowed) or **✕ remove**. The same subject in a *different*
episode is a distinct blunder (allowed).

**Dedup (automatic, backstop).** `load_corrections` also collapses exact duplicates by default
(same episode/seat/**scope/subject**/chosen/correct/category, keeping the latest), so the Tuner,
report and `/blunder-buster` never double-count a legacy/imported repeat. For a decision-scope
record the subject *is* the Anchor frame, so this is the pre-Scope key unchanged.
`python tools/train/dedup_corrections.py` physically compacts the file and lists any residual
conflicts; `dedup=False` reads the raw history.

## Category vocabulary (extensible, by process)

`missed_win`, `missed_ko`, `bad_target`, `prize_mismanagement`, `misattachment`,
`wasted_resource`, `slow_setup`, `missed_evolution`, `overextension`, `bad_retreat`,
`ignored_threat`, `missed_disruption`, `sequencing_error`, `other`. Add a term in
`categories.py` when a real blunder doesn't fit.

Category is **orthogonal to Scope**: it is the *kind* of mistake, Scope is its *size*.
`slow_setup`, `overextension` and `prize_mismanagement` were always match-shaped terms being forced
onto a single Decision — expect Scope to de-overload `sequencing_error`, which absorbed the turn
blunders that had nowhere else to go.

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
- The **live agent trace** (ADR-0019): when the collected `episode-<id>-agent-<seat>-logs.json`
  sits beside the replay, the panel shows *how the agent actually decided* at the frame — each
  option's `score`, fired hypotheses (id + weight), and the decision `margin` — and embeds that
  `@T` record on the saved Correction as `live_trace`. Auto-loaded by the CLI (`telemetry_log`).
- The **posture read** ([ADR-0041](adr/0041-posture-is-observable-in-decision-telemetry.md)): the same
  `@T` record carries `posture` — **who the agent thought it faced** (believed archetype + posterior,
  the applied confidence γ, the matched Matchup Brief). The panel shows it (`🔮 agent read: …`) at the
  decision, and an **"opponent read was wrong"** checkbox flags a matchup misplay: it writes a
  structured `Correction.posture_mismatch` (the intended line still goes in the rationale), so
  `/blunder-buster` ties the blunder to that archetype's Brief / recognition instead of a generic
  weight. Shown in the logged-blunder list as `🔮 read wrong`.
- **Batch mode**: pass a *directory* (e.g. `data/replays/<build_stem>/`) instead of one file and
  the top bar gains `◀ k/N · ep <id> ▶` to step across its Replays (episode-id order) without
  leaving the tool. Each switch re-serves that Replay's frames + live trace and resets "Analyze as"
  to its own-seat (varies per Replay); the right-pane list re-scopes to that episode. One shared
  `corrections.jsonl`; build identity comes from the directory stem (`batch.discover_replays` /
  `batch.load_game`).

## Run

```
python tools/train/blunder_correction.py <replay.json|.gz> --team <ours> --agent mega_starmie
python tools/train/blunder_correction.py data/replays/<build_stem>/ --team <ours> --agent mega_starmie  # batch
python tools/train/blunder_report.py                         # rebuild the trend report
python -m pytest tests/blunder/test_blunder_*.py -q                  # data-spine tests (REQ-BLUNDER-####)
```
