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
re-vendoring. Offline use is guaranteed once vendored (no CDN, no network). The
`postMessage` contract with `@kaggle-environments/core` is an external dependency to be
resolved at build time; if the viewer does not emit its current step, the shell still knows
it because the shell is the navigation authority.
