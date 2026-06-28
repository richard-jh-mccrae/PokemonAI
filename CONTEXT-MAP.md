# Context Map

## Contexts

- [Meta Tracker](./CONTEXT.md) — offline daily pipeline; scrapes replays and reports the deck **Meta** per **Rank Band**.
- [Agent Runtime](./src/common/CONTEXT.md) — deck-agnostic runtime agent code (`src/common/`, shared across agents): the **Pilot** decision architecture, the **Base Value Model**, and **Scouting** (recognize the opponent and produce the **Read**).
- [Agent Checks](./tools/sim/CONTEXT.md) — pre-submission harness (`tools/sim/`) that drives the real cabt simulator to verify an agent's **Playability** and **Deployability** before upload.
- [Training](./tools/train/CONTEXT.md) — offline tooling (`tools/train/`) that turns **Replays** into learning signal; first component is the **blunder inspector** (`blunder_correction`), which emits **Corrections**.
- [Submission & Tracking](./tools/submit/CONTEXT.md) — builds a traceable **Submission** (a **Bundle** + its **Manifest** / **Agent Brief**), uploads it to the Simulation competition, and tracks each agent's state against its **Performance** over time (**Agent History**, **Performance Log**, **Dashboard**).

## Relationships

- **Meta Tracker → Agent Runtime**: the Meta Tracker's meta report (Archetypes + decklists) is compiled *offline* into the shipped `common/scouting/artifact.json` that Scouting loads to recognize opponents — see [ADR-0003](./docs/adr/0003-scouting-knowledge-is-a-shipped-artifact.md) and [ADR-0004](./docs/adr/0004-shared-common-packaged-per-submission.md).
- **Meta Tracker → Agent Runtime (value model)**: the same mined replays are compiled *offline* into the shipped **Base Value Model** (`state → P(win)`) the Pilot uses as Search leaf-eval / Score tiebreaker — see [ADR-0007](./docs/adr/0007-learning-is-one-offline-value-model.md).
- **Meta Tracker → Training**: the blunder inspector loads the same downloaded **Replays** to mark blunders on any Episode featuring our deck (ours or a peer's).
- **Training → Agent Runtime**: **Corrections** become per-decision ranking labels that tune **Hypothesis** weights (Job A) and may author a Hypothesis — see [ADR-0009](./docs/adr/0009-training-methodology.md).
- **Agent Checks → Agent Runtime**: the harness verifies agents built on the Agent Runtime; it runs the *real* cabt env rather than a stand-in — see [ADR-0010](./docs/adr/0010-local-agent-verification-on-cabt-env.md).
- **Agent Checks → packaging**: **Deployability** consumes the **Bundle** assembled by `submit.package` — see [ADR-0004](./docs/adr/0004-shared-common-packaged-per-submission.md).
- **Agent Runtime → Submission & Tracking**: a **Submission** packages a **Bundle** and embeds a **Manifest** read *declaratively* from the agent's **Strategy** + **General Strategy** (Tier lives in `Strategy.params`) — see [ADR-0019](./docs/adr/0019-submissions-are-traceable-and-tracked.md).
- **Training → Submission & Tracking**: each Submission ships the Tuner's `tuned.json` plus a `tuned.meta.json` provenance sidecar, and the agent's **Decision Telemetry** feeds **Corrections** — see [ADR-0018](./docs/adr/0018-applying-tuner-output.md), [ADR-0009](./docs/adr/0009-training-methodology.md).
- **Agent Checks → Submission & Tracking**: `submit` gates on **Deployability** / **Playability** before uploading — see [ADR-0010](./docs/adr/0010-local-agent-verification-on-cabt-env.md).
- **Submission & Tracking → Strategy Writeup**: **Agent History** + **Performance Log** + **Dashboard** are the evidence base for the Strategy-category Writeup — see [ADR-0012](./docs/adr/0012-optimize-for-strategy-category.md). The Writeup's required structure (Kaggle's Winning Model Documentation Guidelines) mapped to our artifacts: [docs/writeup-guidelines.md](./docs/writeup-guidelines.md).
- **Shared vocabulary**: `Archetype`, `Main-line` / `Sub-line` / `Engine Pokémon`, `Meta`, `Rank Band` are defined in **Meta Tracker** and reused verbatim by **Agent Runtime**. Avoid redefining them.
