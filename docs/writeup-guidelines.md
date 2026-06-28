# Strategy Writeup — Documentation Guidelines

What a winning submission must document, and where in this repo each piece comes from. The
structure is Kaggle's
[Winning Model Documentation Guidelines](https://www.kaggle.com/WinningModelDocumentationGuidelines)
(provenance in [Source](#source) below). There are **three standard components**:

- **A · Model Summary** — the written report (Word/PDF). Section A here.
- **B · Submission Model** — a single zip the host can run to reproduce the score. Section B here.
- **C · Kaggle Winner Presentation** — a 1-hour call Kaggle schedules with the host (their
  template). Section C here.

Two adaptations make it ours:

- **We enter the Strategy Category** ([ADR-0012](adr/0012-optimize-for-strategy-category.md)),
  so the deliverable is *documented reasoning*, not a trained model. The guideline's model-centric
  prompts (variable importance, ensembling, train time) are *reinterpreted* into our terms below —
  not skipped.
- **The writeup is generated, not written from scratch.** Our instrumentation — the per-decision
  rationale, Hypothesis `status` transitions, the Correction log, the Dashboard — is the raw
  material; this doc is the checklist saying which artifact fills each required section ("the
  writeup writes itself", [Agent Architecture](agent-architecture.md) → Legibility).

General guidance from the source: the report may be read by **technical and non-technical**
audiences and must inform both; **Word or PDF, English, well-written**; the questions are helpful
guidance — skip irrelevant ones, add useful detail they don't cover.

## A. Model Summary — mapped to our artifacts

| § | What Kaggle asks for | Our source |
|---|---|---|
| **A1 · Background (facts)** | Competition name, team name, private leaderboard score + place; each member's name/location/email. | author-written; score/place from the **Performance Log** / **Agent History** ([submit/CONTEXT](../tools/submit/CONTEXT.md)). |
| **A2 · Background (team)** | Academic/professional background, prior relevant experience, why you entered, time spent, who did what. | author-written. |
| **A3 · Summary** | **4–6 sentences**: training method(s), most important features, tools, train time. | The thesis ([Agent Architecture](agent-architecture.md), [ADR-0012](adr/0012-optimize-for-strategy-category.md)) — a *general competence layer* (the Pilot) plus thin deck doctrine; "method" = rules backbone + offline weight-tuning; tools = `cg` engine, `kaggle-environments`, LightGBM; "train time" = the offline tuner run. |
| **A4 · Features Selection / Engineering** | Most important features; **variable-importance plot of the 10–20** most important + **partial plots for the top 3–5**; how selected; transformations; interactions; external data. | "Features" = decision inputs: **Function Tags** ([card-functions](card-functions.md)), per-deck **Roles**, the **Read** ([scouting](scouting.md)). Variable-importance analog = tuned-vs-default **weight** diffs + hypothesis-firing frequency ([weights](weights.md)); partial-plot analog = a single Hypothesis's effect on one decision (`Pilot.explain` / Decision Telemetry). Selection = how Hypotheses are authored/curated (`/deck-genie`, `/blunder-buster`). External data = downloaded **Replays** / **Meta** ([ADR-0001](adr/0001-data-source.md), [ADR-0011](adr/0011-dataset-source.md)). |
| **A5 · Training Method(s)** | Methods used; whether ensembled; if so, how models are weighted. | [ADR-0009](adr/0009-training-methodology.md) three jobs: **A** weight-tuning (linear ranking / soft-margin perceptron — [tuning/methodology](tuning/methodology.md)), **B** the offline value model (LightGBM), **C** selection (real-ladder A/B gate). "Ensemble" analog = **General Strategy ⊕ deck Strategy** merge (override-by-id) and Tier-0 tactical ⊕ additive Hypothesis scoring; "weights" = the tuned Hypothesis weights. |
| **A6 · Interesting findings** | The most important trick; what set you apart; surprising relationships. | The **Correction** log and its resolved findings (e.g. *attack-is-the-turn-ender → develop first*, *forgo-KO corrections refuted*) — [blunder-tuner](blunder-tuner.md). What sets us apart = a legible rules backbone whose every choice is justified, vs a black box ([ADR-0012](adr/0012-optimize-for-strategy-category.md)). |
| **A7 · Simple Features and Methods** | A subset getting **90–95%** of performance — **< 10 features, one training method**; which model mattered; what the simplified model scores. | **Tier-0** closed-form scoring (printed damage × Weakness vs HP) with the few highest-weight Hypotheses and `search_budget=0` — the simplest config, no lookahead. "What it scores" = a **Battle** pre-filter read ([sim/CONTEXT](../tools/sim/CONTEXT.md)) and the real ladder. |
| **A8 · Model Execution Time** | Time to train and to predict, for both the full and simplified models. | "Train" = the offline tuner / value-trainer run; "predict" = per-move/per-match **Efficiency** ([submit/CONTEXT](../tools/submit/CONTEXT.md)) within the grader sandbox (2 vCPUs, 12.2 GiB RAM, ≈10 min/match — [Agent Checks → Grader resources](agent-checks.md)). |
| **A9 · References** | Citations, sites, posts, external sources. | `cg` engine + pinned `kaggle-environments` ([ADR-0010](adr/0010-local-agent-verification-on-cabt-env.md)); data sources; this repo's ADRs. |

## B. Submission Model — mapped to our artifacts

The reproducibility archive: a single zip with all code, data, and the trained model (**except
Kaggle-supplied data**), well-commented, for a host trying to *re-run* and match the score. Note
the distinction in our project:

- the **Simulation Bundle** is the runtime artifact the grader executes (`main.py` + `deck.csv`
  + `cg/` + `common/`) — the *output* of our build;
- the **B-section archive** is broader: the repo's training code + data-prep that *regenerates*
  that Bundle. B maps to the repo, not just the Bundle.

| § | Kaggle convention | Our equivalent |
|---|---|---|
| **B1 · Single archive** | All code/data/trained model in one zip; Kaggle data excluded. | the repo + the built **Bundle** ([ADR-0004](adr/0004-shared-common-packaged-per-submission.md)); downloaded **Replays** are the excluded Kaggle-derived data. |
| **B2 · README.md** | Hardware, OS/version, 3rd-party software + versions + install, how to train, how to predict, side effects, key assumptions. | repo `README.md` + [docs](.); hardware/OS = the grader sandbox ([Agent Checks](agent-checks.md)) and dev (Windows + Linux, both first-class); "train" = the offline jobs; "predict" = the agent plays a match. |
| **B3 · Configuration files** | Any config files + where they go. | the per-Submission **Manifest** ([ADR-0019](adr/0019-submissions-are-traceable-and-tracked.md)); the Tuner's `tuned.json` + `tuned.meta.json` provenance sidecar ([ADR-0018](adr/0018-applying-tuner-output.md)). |
| **B4 · requirements.txt** | Exact package versions (`pip freeze`) or a Dockerfile. | `tools/sim/requirements.txt` (pins `kaggle-environments==1.30.1` — the ladder version, [ADR-0010](adr/0010-local-agent-verification-on-cabt-env.md)). |
| **B5 · directory_structure.txt** | A `find . -type d` readout. | the repo layout — [CONTEXT-MAP](../CONTEXT-MAP.md) + [Agent Architecture](agent-architecture.md) → Layout. |
| **B6 · SETTINGS.json** | The single place that declares train/test/model/output paths; all I/O reads from it. | the **Manifest** is our single declarative record of every decision-steering input ([ADR-0019](adr/0019-submissions-are-traceable-and-tracked.md)). |
| **B7 · Serialized trained model** | The trained model saved to disk, so prediction needs no re-train. | the shipped `tuned.json` (Hypothesis weights) + the Base Value Model artifact; the **Bundle** *is* the serialized, ready-to-play agent. |
| **B8 · entry_points.md** | Separate `prepare_data` / `train` / `predict` commands. | **prepare**: `tools/meta_tracker` (Replays → meta + scouting + card-functions [+ value-model] artifacts). **train**: `tools/train` tuner (Corrections → `tuned.json`) [+ value trainer]. **"predict"**: `python tools/package_agent.py <deck>` → `python tools/sim/check_agent.py <deck>` (verify, incl. the 197.7 MiB size gate) → `submit`; at runtime `agent(obs)` is the per-decision predictor. |

## C. Kaggle Winner Presentation

A 1-hour call Kaggle schedules with the competition host, on Kaggle's own template. Prep draws
on the same material: the **Dashboard** (growth over time), the Hypothesis `status` transitions,
and the headline **Correction** findings.

## Format

Per the source: **Word or PDF, English, well-written**, informative to technical *and*
non-technical readers. A4 expects **figures** (our weight-diff / hypothesis-firing chart), not
prose alone. Section A is the report; B is the runnable archive; C is the live call.

## Source

Full guideline text provided by the user from the live Kaggle page (JS-rendered, not directly
fetchable); the section structure above (A1–A9, B1–B8, the three components) is verbatim from it.
Kaggle notes the requirements "may be subject to revision for each competition" — confirm against
the competition rules / your Kaggle contact during close-out.
