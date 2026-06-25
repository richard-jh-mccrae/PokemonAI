# ADR-0014: Blunder inspector reuses the official cabt visualizer, embedded in a tagging shell

**Context.** The blunder inspector (`tools/train/`, [ADR-0009](0009-training-methodology.md))
must let us step through a replay **offline** with the *same* visuals the Kaggle site shows.
The cabt env exposes the official renderer hook (`env.render(mode="html")` →
`html_renderer()` reading `envs/cabt/visualizer/default/dist/index.html`), but the built
visual asset is **stripped from the PyPI wheel** — locally `html_renderer()` returns `""`.
The visualizer *source* (a Vite/TypeScript app over `@kaggle-environments/core`, fed replay
data via `window.postMessage`) does ship in the kaggle-environments GitHub repo.

**Decision.** Vendor and build the official visualizer (pinned to the installed env version,
`1.30.1`) into the path `html_renderer()` expects, and **embed it as an iframe inside a thin
"tagging shell" (parent window)**. The shell owns timeline navigation (play/pause/step/scrub)
and feeds the replay to the viewer via `postMessage`; the official viewer renders the board
pixel-identical to online; the shell's side panel authors the **Correction**. Because the
shell drives navigation, it always knows the current step being tagged.

**Considered options.**
- **Render-only (no tagging seam)** — call `env.render` and view the bare HTML. Rejected: no
  place to attach tagging; the whole point is authoring Corrections.
- **Build our own renderer in pure HTML/JS from the replay `visualize`/`current` data** —
  rejected: forfeits the hard requirement of being *identical to online*, and re-derives a
  board renderer the competition already maintains. Kept as the fallback only if the upstream
  viewer ever becomes unbuildable.

**Consequences.** Introduces a **one-time Node/pnpm build + a vendored JS bundle into an
otherwise Python-only repo** — a deliberate deviation (Node v24 + corepack are present
locally). The viewer is **pinned to the env version**; bumping `kaggle-environments` means
re-vendoring. The shell feeds the replay via `postMessage({replay})` (contract confirmed in
`@kaggle-environments/core`); the shell is the navigation authority.

## Amendment (corrected after building): two viewers, only one is offline

The premise that vendoring yields a *pixel-identical-to-online* viewer was **wrong**. The
OSS `visualizer/default` is a **plain canvas board** (text + lines, no card art). The
colorful dynamic viewer shown online is a **separate, closed, HEROZ-hosted web app**
(`https://ptcgvis.heroz.jp/Visualizer/Replay/<EpisodeId>/<seat>`); the OSS board merely
renders "Open Visualizer" buttons that **POST the replay JSON** to it. So:

- **Offline** = the vendored plain board (no card art).
- **Colorful, "as online"** = HEROZ-hosted, **online-only**, opened via form POST (works on
  *any* replay — own/peer/local — since the data travels in the POST body).

The shell surfaces a **colorful** action (embed in the iframe if HEROZ permits framing,
else new tab). HEROZ's page is **cross-origin**, so tagging cannot be injected into it and
its current step cannot be read — the user reads the colorful viewer and tags the matching
**Decision** in our panel (correlated by turn/frame/context). The strict-offline requirement
and the colorful viewer are therefore **mutually exclusive**; the tool keeps the plain board
as the offline default and the colorful viewer one click away.
